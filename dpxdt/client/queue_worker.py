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
from dpxdt.client import fetch_worker
from dpxdt.client import timer_worker
from dpxdt.client import workers


gflags.DEFINE_string(
    'queue_server_prefix', None,
    'URL prefix of where the work queue server is located, such as '
    '"https://www.example.com/api/work_queue". This should use HTTPS if '
    'possible, since API requests send credentials using HTTP basic auth.')

gflags.DEFINE_integer(
    'queue_poll_seconds', 60,
    'How often to poll an empty work queue for new tasks.')


class Error(Exception):
    """Base-class for exceptions in this module."""


class GiveUpAfterAttemptsError(Error):
    """Exception indicates the task should give up after N attempts."""

    def __init__(self, max_attempts, *args, **kwargs):
        """Initializer.

        Args:
            max_attempts: Maximum number of attempts to make for this task,
                inclusive. So 2 means try two times and then retire the task.
            *args, **kwargs: Optional Exception arguments.
        """
        Exception.__init__(self, *args, **kwargs)
        self.max_attempts = max_attempts


class HeartbeatError(Error):
    """Reporting the status of a task in progress failed for some reason."""


# TODO: Split heartbeats out into a separate FetchItem thread so we don't
# gum-up the important workflows with messages that aren't critical.

class HeartbeatWorkflow(workers.WorkflowItem):
    """Reports the status of a RemoteQueueWorkflow to the API server.

    Args:
        queue_url: Base URL of the work queue.
        task_id: ID of the task to update the heartbeat status message for.
        message: Heartbeat status message to report.
        index: Index for the heartbeat message. Should be at least one
            higher than the last heartbeat message.
    """

    fire_and_forget = True

    def run(self, queue_url, task_id, message, index):
        call = yield fetch_worker.FetchItem(
            queue_url + '/heartbeat',
            post={
                'task_id': task_id,
                'message': message,
                'index': index,
            },
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise HeartbeatError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise HeartbeatError('Bad response: %r' % call)


class DoTaskWorkflow(workers.WorkflowItem):
    """Runs a local workflow for a task and marks it done in the remote queue.

    Args:
        queue_url: Base URL of the work queue.
        local_queue_workflow: WorkflowItem sub-class to create using parameters
            from the remote work payload that will execute the task.
        task: JSON payload of the task.
    """

    fire_and_forget = True

    def run(self, queue_url, local_queue_workflow, task):
        logging.info('Starting work item from queue_url=%r, '
                     'task=%r, workflow=%r',
                     queue_url, task, local_queue_workflow)

        # Define a heartbeat closure that will return a workflow for
        # reporting status. This will auto-increment the index on each
        # call, so only the latest update will be saved.
        index = [0]
        task_id = task['task_id']
        def heartbeat(message):
            next_index = index[0]
            index[0] = next_index + 1
            return HeartbeatWorkflow(
                queue_url, task_id, message, next_index)

        payload = task['payload']
        payload.update(heartbeat=heartbeat)

        try:
            yield local_queue_workflow(**payload)
        except Exception, e:
            logging.exception('Exception while processing work from '
                              'queue_url=%r, task=%r', queue_url, task)
            yield heartbeat('Task failed. %s: %s' %
                            (e.__class__.__name__, str(e)))

            if (isinstance(e, GiveUpAfterAttemptsError) and
                    task['lease_attempts'] >= e.max_attempts):
                logging.warning(
                    'Hit max attempts on task=%r, giving up',
                    task)
            else:
                # The task has legimiately failed. Do not mark the task as
                # finished. Let it retry in the queue again.
                return

        try:
            finish_item = yield fetch_worker.FetchItem(
                queue_url + '/finish',
                post={'task_id': task_id},
                username=FLAGS.release_client_id,
                password=FLAGS.release_client_secret)
        except Exception, e:
            logging.error('Could not finish work with '
                          'queue_url=%r, task=%r. %s: %s',
                          queue_url, task, e.__class__.__name__, e)
        else:
            if finish_item.json and finish_item.json.get('error'):
                logging.error('Could not finish work with '
                              'queue_url=%r, task=%r. %s',
                              queue_url, finish_item.json['error'], task)
            else:
                logging.info('Finished work item with queue_url=%r, '
                             'task_id=%r', queue_url, task_id)


class RemoteQueueWorkflow(workers.WorkflowItem):
    """Fetches tasks from a remote queue periodically, runs them locally.

    Args:
        queue_name: Name of the queue to fetch from.
        local_queue_workflow: WorkflowItem sub-class to create using parameters
            from the remote work payload that will execute the task.
        max_tasks: Maximum number of tasks to have in flight at any time.
    """

    def run(self, queue_name, local_queue_workflow, max_tasks):
        queue_url = '%s/%s' % (FLAGS.queue_server_prefix, queue_name)
        outstanding = []

        while True:
            next_count = max_tasks - len(outstanding)
            next_tasks = []

            if next_count > 0:
                logging.info(
                    'Fetching %d tasks from queue_url=%r for workflow=%r',
                    next_count, queue_url, local_queue_workflow)
                try:
                    next_item = yield fetch_worker.FetchItem(
                        queue_url + '/lease',
                        post={'count': next_count},
                        username=FLAGS.release_client_id,
                        password=FLAGS.release_client_secret)
                except Exception, e:
                    logging.error(
                        'Could not fetch work from queue_url=%r. %s: %s',
                        queue_url, e.__class__.__name__, e)
                else:
                    if next_item.json:
                        if next_item.json.get('error'):
                            logging.error(
                                'Could not fetch work from queue_url=%r. %s',
                                queue_url, next_item.json['error'])
                        elif next_item.json['tasks']:
                            next_tasks = next_item.json['tasks']

            # TODO: Add rate-limiting to local task starts, so we space out
            # when we start subprocesses on the server.
            for task in next_tasks:
                item = yield DoTaskWorkflow(
                    queue_url, local_queue_workflow, task)
                outstanding.append(item)

            yield timer_worker.TimerItem(FLAGS.queue_poll_seconds)
            outstanding[:] = [x for x in outstanding if not x.done]
