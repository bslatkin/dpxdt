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

"""Workers that consumer a release server's work queue."""

import logging

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
import capture_worker
import pdiff_worker
import release_worker
import workers


gflags.DEFINE_string(
    'pdiff_queue_url', None,
    'URL of remote perceptual diff work queue to process.')

gflags.DEFINE_string(
    'capture_queue_url', None,
    'URL of remote webpage capture work queue to process.')


class Error(Exception):
    """Base-class for exceptions in this module."""

class HeartbeatError(Error):
    """Reporting the status of a task in progress failed for some reason."""

class PdiffFailedError(Error):
    """Running a perceptual diff failed for some reason."""

class CaptureFailedError(Error):
    """Capturing a webpage screenshot failed for some reason."""



# TODO: Split this out into a separate FetchItem thread so we don't gum-up
# the important workflows with messages that aren't critical.

class HeartbeatWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, queue_heartbeat_url, task_id, message, index):
        call = yield workers.FetchItem(
            queue_url + '/heartbeat',
            post={
                'task_id': task_id,
                'message': message,
                'index': index,
            })

        if call.json and call.json.get('error'):
            raise HeartbeatError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise HeartbeatError('Bad response: %r' % call)


class RemoteQueueWorkflow(WorkflowItem):
    """Runs a local workflow based on work items in a remote queue.

    Args:
        queue_url: Base URL of the work queue.
        local_queue_workflow: WorkflowItem sub-class to create using parameters
            from the remote work payload that will execute the task.
        poll_period: How often, in seconds, to poll the queue when it's
            found to be empty.
    """

    def run(self, queue_url, local_queue_workflow, poll_period=60):
        while True:
            next_item = yield workers.FetchItem(queue_url + '/lease', post={})

            something_to_do = False
            if next_item.json and next_item.json['error']:
                logging.error('Could not fetch work from queue_url=%r. '
                              '%s', queue_url, next_item.json['error'])
            elif next_item.json and next_item.json['tasks']:
                something_to_do = True

            if not something_to_do:
                yield workers.TimerItem(poll_period)
                continue

            task_list = next_item.json['tasks']
            assert len(task_list) == 1
            task = task_list[0]

            task_id = task.pop('task_id')
            logging.debug('Starting work item from queue_url=%r, '
                          'task_id=%r, payload=%r, workflow=%r',
                          queue_url, task_id, task,
                          local_queue_workflow)

            # Define a heartbeat closure that will return a workflow for
            # reporting status. This will auto-increment the index on each
            # call, so only the latest update will be saved.
            # TODO: Make this fire-and-forget.
            index = [0]
            def heartbeat(message):
                next_index = index[0]
                index[0] = next_index + 1
                logging.debug('queue_url=%r, task_id=%r, message: %s',
                              queue_url, task_id, message)
                return HeartbeatWorkflow(
                    queue_url + '/heartbeat', task_id, message, next_index)

            task.update(heartbeat=heartbeat)

            try:
                yield local_queue_workflow(**task)
            except Exception, e:
                logging.exception('Exception while processing work from '
                                  'queue_url=%r, task_id=%r',
                                  queue_url, task_id)
                yield heartbeat('Task failed. %s: %s' %
                                (e.__class__.__name__, str(e)))
                continue

            finish_item = yield workers.FetchItem(
                queue_url + '/finish, post={'task_id': task_id})
            if finish_item.json and finish_item.json['error']:
                logging.error('Could not finish work with '
                              'queue_url=%r, task_id=%r. %s',
                              queue_url, finish_item.json['error'], task_id)

            logging.debug('Finished work item with queue_url=%r, '
                          'task_id=%r', queue_url, task_id)


class DoPdiffQueueWorkflow(WorkflowItem):
    """TODO"""

    def run(self, build_id=None, release_name=None, release_number=None,
            run_name=None, reference_url=None, run_url=None, heartbeat=None):
        output_path = tempfile.mkdtemp()
        try:
            ref_path = os.path.join(output_path, 'ref')
            run_path = os.path.join(output_path, 'run')
            diff_path = os.path.join(output_path, 'diff')
            log_path = os.path.join(output_path, 'log')

            yield heartbeat('Fetching reference and run images')
            yield [
                workers.FetchItem(reference_url, result_path=ref_path)
                workers.FetchItem(run_url, result_path=run_path)
            ]

            yield heartbeat('Running perceptual diff process')
            pdiff = yield pdiff_worker.PdiffItem(
                log_path, ref_path, run_path, diff_path)

            output_exists = os.path.isfile(diff_path)
            if not output_exists and pdiff.returncode != 0:
                raise PdiffFailedError('output_exists=%r, returncode=%r' %
                                       (output_exists, pdiff.returncode))

            yield heartbeat('Reporting diff status to server')
            yield release_worker.ReportPdiffWorkflow(
                build_id, release_name, release_number, run_name,
                diff_path, log_path)
        finally:
            shutil.rmtree(output_path, True)


class DoCaptureQueueWorkflow(WorkflowItem):
    """TODO"""

    def run(self, build_id=None, release_name=None, release_number=None,
            run_name=None, config_url=None, heartbeat=None):
        output_path = tempfile.mkdtemp()
        try:
            image_path = os.path.join(output_path, 'capture')
            log_path = os.path.join(output_path, 'log')
            config_path = os.path.join(output_path, 'config')

            yield heartbeat('Fetching webpage capture config')
            yield workers.FetchItem(
                config_url, result_path=config_path)

            yield heartbeat('Running webpage capture process')

            capture = yield capture_worker.CaptureItem(
                log_path, config_path, image_path)
            if capture.returncode != 0:
                raise CaptureFailedError('returncode=%r' % capture.returncode)

            yield heartbeat('Reporting capture status to server')
            yield release_worker.ReportRunWorkflow(
                build_id, release_name, release_number, run_name,
                image_path, log_path, config_path)
        finally:
            shutil.rmtree(output_path, True)


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    # TODO: Add a flag to support up to N parallel queue workers.
    if FLAGS.pdiff_queue_url:
        item = RemoteQueueWorkflow(
            FLAGS.pdiff_queue_url,
            release_worker.DoPdiffQueueWorkflow)
        item.root = True
        coordinator.input_queue.put(item)

    if FLAGS.capture_queue_url:
        item = RemoteQueueWorkflow(
            FLAGS.capture_queue_url,
            release_worker.DoCaptureQueueWorkflow)
        item.root = True
        coordinator.input_queue.put(item)
