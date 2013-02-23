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
import pdiff_worker
import release_worker
import workers


gflags.DEFINE_string(
    'pdiff_queue_url', None,
    'URL of remote perceptual diff work queue to process.')


class RemoteQueueWorkflow(WorkflowItem):
    """Runs a local workflow based on work items in a remote queue.

    Args:
        queue_lease_url: URL to POST to for leasing new tasks.
        queue_finish_url: URL to POST to for finishing an existing task.
        local_queue_workflow: WorkflowItem sub-class to create using parameters
            from the remote work payload that will execute the task.
        poll_period: How often, in seconds, to poll the queue when it's
            found to be empty.
    """

    def run(self, queue_lease_url, queue_finish_url, local_queue_workflow,
            poll_period=60):
        while True:
            next_item = yield workers.FetchItem(queue_lease_url, post={})

            something_to_do = False
            if next_item.json and next_item.json['error']:
                logging.error('Could not fetch work from queue_lease_url=%r. '
                              '%s', queue_lease_url, next_item.json['error'])
            elif next_item.json and next_item.json['tasks']:
                something_to_do = True

            if not something_to_do:
                yield workers.TimerItem(poll_period)
                continue

            task_list = next_item.json['tasks']
            assert len(task_list) == 1
            task = task_list[0]

            task_id = task.pop('task_id')
            logging.debug('Starting work item from queue_lease_url=%r, '
                          'task_id=%r, payload=%r, workflow=%r',
                          queue_finish_url, task_id, task,
                          local_queue_workflow)

            try:
                yield local_queue_workflow(**task)
            except Exception:
                logging.exception('Exception while processing work from '
                                  'queue_lease_url=%r, task_id=%r',
                                  queue_lease_url, task_id)
                continue

            finish_item = yield workers.FetchItem(
                queue_finish_url, post={'task_id': task_id})
            if finish_item.json and finish_item.json['error']:
                logging.error('Could not finish work with '
                              'queue_finish_url=%r, task_id=%r. %s',
                              queue_finish_url, finish_item.json['error'],
                              task_id)

            logging.debug('Finished work item with queue_finish_url=%r, '
                          'task_id=%r', queue_finish_url, task_id)


class DoPdiffQueueWorkflow(WorkflowItem):
    """TODO"""

    def run(self, build_id=None, release_name=None, release_number=None,
            run_name=None, reference_url=None, run_url=None):
        output_path = tempfile.mkdtemp()
        try:
            ref_path = os.path.join(output_path, 'ref')
            run_path = os.path.join(output_path, 'run')
            diff_path = os.path.join(output_path, 'diff')
            log_path = os.path.join(output_path, 'log')

            ref_item, run_item = yield [
                workers.FetchItem(reference_url, result_path=ref_path)
                workers.FetchItem(run_url, result_path=run_path)
            ]

            pdiff = yield pdiff_worker.PdiffItem(
                log_path, ref_path, run_path, diff_path)
            if not os.path.isfile(diff_path) and pdiff.returncode != 0:
                # TODO: Real exception
                assert False, 'Error!'

            yield release_worker.ReportPdiffWorkflow(
                build_id, release_name, release_number, run_name,
                diff_path, log_path)
        finally:
            shutil.rmtree(output_path, True)


class DoCaptureQueueWorkflow(WorkflowItem):
    """TODO"""

    def run(self, build_id, name, number, config_url):
        # create a temp dir
        # fetch the config
        # run capture_worker.CaptureItem on the config
        # run ReportRunWorkflow on the files
        # delete temp dir


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    if FLAGS.pdiff_queue_url:
        # TODO: Add a flag to support up to N parallel queue workers.
        item = RemoteQueueWorkflow(
            FLAGS.pdiff_queue_url = '/lease',
            FLAGS.pdiff_queue_url = '/finish',
            release_worker.DoPdiffQueueWorkflow)
        item.root = True

    coordinator.input_queue.put(item)
