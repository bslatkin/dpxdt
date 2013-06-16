#!/usr/bin/env python
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Workers for driving screen captures, perceptual diffs, and related work."""

import Queue
import base64
import heapq
import json
import logging
import shutil
import subprocess
import sys
import threading
import time
import urllib
import urllib2

# Local Libraries
import gflags
FLAGS = gflags.FLAGS
import poster.encode
import poster.streaminghttp
poster.streaminghttp.register_openers()


gflags.DEFINE_float(
    'fetch_frequency', 1.0,
    'Maximum number of fetches to make per second per thread.')

gflags.DEFINE_float(
    'polltime', 1.0,
    'How long to sleep between polling for work or subprocesses')


class Error(Exception):
    """Base class for exceptions in this module."""

class TimeoutError(Exception):
    """Subprocess has taken too long to complete and was terminated."""



class WorkItem(object):
    """Base work item that can be handled by a worker thread."""

    def __init__(self):
        self.error = None

    @staticmethod
    def _print_tree(obj):
        if isinstance(obj, dict):
            result = []
            for key, value in obj.iteritems():
                result.append("%s=%s" % (key, WorkItem._print_tree(value)))
            return '{%s}' % ', '.join(result)
        else:
            value_str = repr(obj)
            if len(value_str) > 100:
                return '%s...%s' % (value_str[:100], value_str[-1])
            else:
                return value_str

    def _get_dict_for_repr(self):
        return self.__dict__

    def __repr__(self):
        return '%s.%s(%s)' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self._print_tree(self._get_dict_for_repr()))

    def check_result(self):
        # TODO: For WorkflowItems, remove generator.throw(*item.error) from
        # the stack trace since it's noise. General approach outlined here:
        # https://github.com/mitsuhiko/jinja2/blob/master/jinja2/debug.py
        if self.error:
            raise self.error[0], self.error[1], self.error[2]


class WorkerThread(threading.Thread):
    """Base worker thread that handles items one at a time."""

    def __init__(self, input_queue, output_queue):
        """Initializer.

        Args:
            input_queue: Queue this worker consumes work from.
            output_queue: Queue where this worker puts new work items, if any.
        """
        threading.Thread.__init__(self)
        self.daemon = True
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.interrupted = False
        self.polltime = FLAGS.polltime

    def stop(self):
        """Stops the thread but does not join it."""
        if self.interrupted:
            return
        self.interrupted = True

    def run(self):
        while not self.interrupted:
            try:
                item = self.input_queue.get(True, self.polltime)
            except Queue.Empty:
                self.handle_nothing()
                continue

            try:
                next_item = self.handle_item(item)
            except Exception, e:
                item.error = sys.exc_info()
                logging.debug('%s error item=%r', self.worker_name, item)
                self.output_queue.put(item)
            else:
                logging.debug('%s processed item=%r', self.worker_name, item)
                if next_item:
                    self.output_queue.put(next_item)
            finally:
                self.input_queue.task_done()

    @property
    def worker_name(self):
        return '%s:%s' % (self.__class__.__name__, self.ident)

    def handle_nothing(self):
        """Runs whenever there are no items in the queue."""
        pass

    def handle_item(self, item):
        """Handles a single item.

        Args:
            item: WorkItem to process.

        Returns:
            A WorkItem that should go on the output queue. If None, then
            the provided work item is considered finished and no
            additional work is needed.
        """
        raise NotImplemented


class FetchItem(WorkItem):
    """Work item that is handled by fetching a URL."""

    def __init__(self, url, post=None, timeout_seconds=30, result_path=None,
                 username=None, password=None):
        """Initializer.

        Args:
            url: URL to fetch.
            post: Optional. Dictionary of post parameters to include in the
                request, with keys and values coerced to strings. If any
                values are open file handles, the post data will be formatted
                as multipart/form-data.
            timeout_seconds: Optional. How long until the fetch should timeout.
            result_path: When supplied, the output of the fetch should be
                streamed to a file on disk with the given path. Use this
                to prevent many fetches from causing memory problems.
            username: Optional. Username to use for the request, for
                HTTP basic authentication.
            password: Optional. Password to use for the request, for
                HTTP basic authentication.
        """
        WorkItem.__init__(self)
        self.url = url
        self.post = post
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.result_path = result_path
        self.status_code = None
        self.data = None
        self.headers = None
        self._data_json = None

    def _get_dict_for_repr(self):
        result = self.__dict__.copy()
        if result.get('password'):
            result['password'] = 'ELIDED'
        return result

    @property
    def json(self):
        """Returns de-JSONed data or None if it's a different content type."""
        if self._data_json:
            return self._data_json

        if not self.data or self.headers.gettype() != 'application/json':
            return None

        self._data_json = json.loads(self.data)
        return self._data_json


class FetchThread(WorkerThread):
    """Worker thread for fetching URLs."""

    def handle_item(self, item):
        start_time = time.time()

        if item.post is not None:
            adjusted_data = {}
            use_form_data = False

            for key, value in item.post.iteritems():
                if value is None:
                    continue
                if isinstance(value, file):
                    use_form_data = True
                adjusted_data[key] = value

            if use_form_data:
                datagen, headers = poster.encode.multipart_encode(
                    adjusted_data)
                request = urllib2.Request(item.url, datagen, headers)
            else:
                request = urllib2.Request(
                    item.url, urllib.urlencode(adjusted_data))
        else:
            request = urllib2.Request(item.url)

        if item.username:
            credentials = base64.b64encode(
                '%s:%s' % (item.username, item.password))
            request.add_header('Authorization', 'Basic %s' % credentials)

        try:
            try:
                conn = urllib2.urlopen(request, timeout=item.timeout_seconds)
            except urllib2.HTTPError, e:
                conn = e
            except urllib2.URLError, e:
                item.status_code = 400
                return item

            try:
                item.status_code = conn.getcode()
                item.headers = conn.info()
                if item.result_path:
                    with open(item.result_path, 'wb') as result_file:
                        shutil.copyfileobj(conn, result_file)
                else:
                    item.data = conn.read()
            finally:
                conn.close()

            return item
        finally:
            end_time = time.time()
            wait_duration = (1.0 / FLAGS.fetch_frequency) - (
                end_time - start_time)
            if wait_duration > 0:
                logging.debug('Rate limiting URL fetch for %f seconds',
                              wait_duration)
                time.sleep(wait_duration)


class ProcessItem(WorkItem):
    """Work item that is handled by running a subprocess."""

    def __init__(self, log_path, timeout_seconds=30):
        """Initializer.

        Args:
            log_path: Path to where output from this subprocess should be
                written.
            timeout_seconds: How long before the process should be force
                killed.
        """
        WorkItem.__init__(self)
        self.log_path = log_path
        self.timeout_seconds = timeout_seconds
        self.return_code = None


class ProcessThread(WorkerThread):
    """Worker thread that runs subprocesses."""

    def get_args(self, item):
        raise NotImplemented

    def handle_item(self, item):
        start_time = time.time()
        with open(item.log_path, 'w') as output_file:
            args = self.get_args(item)
            logging.debug('%s item=%r Running subprocess: %r',
                          self.worker_name, item, args)
            try:
                process = subprocess.Popen(
                    args,
                    stderr=subprocess.STDOUT,
                    stdout=output_file,
                    close_fds=True)
            except:
                logging.error('%s item=%r Failed to run subprocess: %r',
                              self.worker_name, item, args)
                raise

            while True:
                process.poll()
                if process.returncode is None:
                    now = time.time()
                    run_time = now - start_time
                    if run_time > item.timeout_seconds or self.interrupted:
                        process.kill()
                        raise TimeoutError(
                            'Sent SIGKILL to item=%r, pid=%s, run_time=%s' %
                            (item, process.pid, run_time))

                    time.sleep(FLAGS.polltime)
                    continue

                item.returncode = process.returncode

                return item


class TimerItem(WorkItem):
    """Work item for waiting some period of time before returning."""

    def __init__(self, delay_seconds):
        WorkItem.__init__(self)
        self.delay_seconds = delay_seconds
        self.ready_time = time.time() + delay_seconds


class TimerThread(WorkerThread):
    """"Worker thread that tracks many timers."""

    def __init__(self, *args):
        """Initializer."""
        WorkerThread.__init__(self, *args)
        self.timers = []

    def handle_nothing(self):
        now = time.time()
        while self.timers:
            ready_time, _ = self.timers[0]
            wait_time = ready_time - now
            if wait_time <= 0:
                _, item = heapq.heappop(self.timers)
                self.output_queue.put(item)
            else:
                # Wait for new work up to the point that the earliest
                # timer is ready to fire.
                self.polltime = wait_time
                return

        # Nothing to do, use the default poll time.
        self.polltime = FLAGS.polltime

    def handle_item(self, item):
        heapq.heappush(self.timers, (item.ready_time, item))
        self.handle_nothing()


class WorkflowItem(WorkItem):
    """Work item for coordinating other work items.

    To use: Sub-class and override run(). Yield WorkItems you want processed
    as part of this workflow. Exceptions in child workflows will be reinjected
    into the run() generator at the yield point. Results will be available on
    the WorkItems returned by yield statements. Yield a list of WorkItems
    to do them in parallel. The first error encountered for the whole list
    will be raised if there's an exception.
    """

    def __init__(self, *args, **kwargs):
        WorkItem.__init__(self)
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.done = False
        self.root = False

    def run(self, *args, **kwargs):
        yield 'Yo dawg'


class Barrier(list):
    """Barrier for running multiple WorkItems in parallel."""

    def __init__(self, workflow, generator, work):
        """Initializer.

        Args:
            workflow: WorkflowItem instance this is for.
            generator: Current state of the WorkflowItem's generator.
            work: Next set of work to do. May be a single WorkItem object or
                a list or tuple that contains a set of WorkItems to run in
                parallel.
        """
        list.__init__(self)
        self.workflow = workflow
        self.generator = generator
        if isinstance(work, (list, tuple)):
            self[:] = list(work)
            self.was_list = True
        else:
            self[:] = [work]
            self.was_list = False
        self.remaining = len(self)
        self.error = None

    def get_item(self):
        """Returns the item to send back into the workflow generator."""
        if self.was_list:
            blocking_items = self[:]
            self[:] = []
            for item in blocking_items:
                if isinstance(item, WorkflowItem):
                    self.append(item.result)
                else:
                    self.append(item)
            return self
        else:
            return self[0]

    def finish(self, item):
        """Marks the given item that is part of the barrier as done."""
        self.remaining -= 1
        if item.error and not self.error:
            self.error = item.error


# TODO: Add FireAndForget class that can wrap a WorkItem. Instructs the
# WorkflowThread to run the given WorkItem on its target queue, but to
# ignore all exceptions it raises and not wait until it completes to let
# the current worker to continue processing. The result of the yield will
# be None. Use this to add heart-beat work items to background queues.
# Include a locally incrementing number so the server side can ignore
# heartbeat updates that are old, in the case the queue gets out of order.


class Return(Exception):
    """Raised in WorkflowItem.run to return a result to the caller."""

    def __init__(self, result=None):
        """Initializer.

        Args:
            result: Result of a WorkflowItem, if any.
        """
        self.result = result


class WorkflowThread(WorkerThread):
    """Worker thread for running workflows."""

    def __init__(self, input_queue, output_queue):
        """Initializer.

        Args:
            input_queue: Queue this worker consumes work from. These should be
                WorkflowItems to process, or any WorkItems registered with this
                class using the register() method.
            output_queue: Queue where this worker puts finished work items,
                if any.
        """
        WorkerThread.__init__(self, input_queue, output_queue)
        self.pending = {}
        self.work_map = {}
        self.worker_threads = []
        self.register(WorkflowItem, input_queue)

    # TODO: Implement drain, to let all existing work finish but no new work
    # allowed at the top of the funnel.

    def start(self):
        """Starts the coordinator thread and all related worker threads."""
        assert not self.interrupted
        for thread in self.worker_threads:
            thread.start()
        WorkerThread.start(self)

    def stop(self):
        """Stops the coordinator thread and all related threads."""
        if self.interrupted:
            return
        for thread in self.worker_threads:
            thread.interrupted = True
        self.interrupted = True

    def join(self):
        """Joins the coordinator thread and all worker threads."""
        for thread in self.worker_threads:
            thread.join()
        WorkerThread.join(self)

    def wait_until_interrupted(self):
        """Waits until this worker is interrupted by a terminating signal."""
        while True:
            try:
                item = self.output_queue.get(True, 1)
            except Queue.Empty:
                continue
            except KeyboardInterrupt:
                logging.debug('Exiting')
                return
            else:
                item.check_result()
                return

    def register(self, work_type, queue):
        """Registers where work for a specific type can be executed.

        Args:
            work_type: Sub-class of WorkItem to register.
            queue: Queue instance where WorkItems of the work_type should be
                enqueued when they are yielded by WorkflowItems being run by
                this worker.
        """
        self.work_map[work_type] = queue

    def handle_item(self, item):
        if isinstance(item, WorkflowItem) and not item.done:
            workflow = item
            try:
                generator = item.run(*item.args, **item.kwargs)
            except TypeError, e:
                raise TypeError('%s: item=%r', e, item)
            item = None
        else:
            barrier = self.pending.pop(item)
            barrier.finish(item)
            if barrier.remaining and not barrier.error:
                return
            item = barrier.get_item()
            workflow = barrier.workflow
            generator = barrier.generator

        while True:
            logging.debug('Transitioning workflow=%r, generator=%r, item=%r',
                          workflow, generator, item)
            try:
                try:
                    if item is not None and item.error:
                        next_item = generator.throw(*item.error)
                    elif isinstance(item, WorkflowItem):
                        next_item = generator.send(item.result)
                    else:
                        next_item = generator.send(item)
                except StopIteration:
                    workflow.done = True
                except Return, e:
                    workflow.done = True
                    workflow.result = e.result
                except Exception, e:
                    workflow.done = True
                    workflow.error = sys.exc_info()
            finally:
                if workflow.done:
                    if workflow.root:
                        # Root workflow finished. This goes to the output
                        # queue so it can be received by the main thread.
                        return workflow
                    else:
                        # Sub-workflow finished. Reinject it into the
                        # workflow so a pending parent can catch it.
                        self.input_queue.put(workflow)
                        return

            # If a returned barrier is empty, immediately progress the
            # workflow.
            barrier = Barrier(workflow, generator, next_item)
            if barrier:
                break
            else:
                item = None

        for item in barrier:
            if isinstance(item, WorkflowItem):
                target_queue = self.input_queue
            else:
                target_queue = self.work_map[type(item)]
            self.pending[item] = barrier
            target_queue.put(item)


def get_coordinator():
    """Creates a coordinator and returns it."""
    fetch_queue = Queue.Queue()
    timer_queue = Queue.Queue()
    workflow_queue = Queue.Queue()
    complete_queue = Queue.Queue()

    coordinator = WorkflowThread(workflow_queue, complete_queue)
    coordinator.register(FetchItem, fetch_queue)
    coordinator.register(TimerItem, timer_queue)

    # TODO: Make number of threads configurable.
    # TODO: Enable multiple coodinator threads.
    coordinator.worker_threads = [
        FetchThread(fetch_queue, workflow_queue),
        FetchThread(fetch_queue, workflow_queue),
        TimerThread(timer_queue, workflow_queue),
    ]

    return coordinator
