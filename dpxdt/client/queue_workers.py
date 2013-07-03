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
import os
import shutil
import tempfile

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt import constants
import capture_worker
import fetch_worker
import pdiff_worker
import process_worker
import release_worker
import timer_worker
import workers


gflags.DEFINE_string(
    'queue_server_prefix', None,
    'URL prefix of where the work queue server is located, such as '
    '"https://www.example.com/api/work_queue". This should use HTTPS if '
    'possible, since API requests send credentials using HTTP basic auth.')

gflags.DEFINE_integer(
    'capture_task_max_attempts', 3,
    'Maximum number of attempts for processing a capture task.')

gflags.DEFINE_integer(
    'pdiff_task_max_attempts', 3,
    'Maximum number of attempts for processing a pdiff task.')

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

class PdiffFailedError(GiveUpAfterAttemptsError):
    """Running a perceptual diff failed for some reason."""

class CaptureFailedError(GiveUpAfterAttemptsError):
    """Capturing a webpage screenshot failed for some reason."""


# TODO: Split this out into a separate FetchItem thread so we don't gum-up
# the important workflows with messages that aren't critical.

class HeartbeatWorkflow(workers.WorkflowItem):
    """Reports the status of a RemoteQueueWorkflow to the API server.

    Args:
        queue_url: Base URL of the work queue.
        task_id: ID of the task to update the heartbeat status message for.
        message: Heartbeat status message to report.
        index: Index for the heartbeat message. Should be at least one
            higher than the last heartbeat message.
    """

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



class RemoteQueueWorkflow(workers.WorkflowItem):
    """Runs a local workflow based on work items in a remote queue.

    Args:
        queue_url: Base URL of the work queue.
        local_queue_workflow: WorkflowItem sub-class to create using parameters
            from the remote work payload that will execute the task.
        poll_period: How often, in seconds, to poll the queue when it's
            found to be empty.
    """

    def run(self, queue_url, local_queue_workflow, poll_period):
        while True:
            try:
                next_item = yield fetch_worker.FetchItem(
                    queue_url + '/lease',
                    post={},
                    username=FLAGS.release_client_id,
                    password=FLAGS.release_client_secret)
            except Exception, e:
                logging.error('Could not fetch work from queue_url=%r. %s: %s',
                              queue_url, e.__class__.__name__, e)
                next_item = None

            something_to_do = False
            if next_item:
                if next_item.json and next_item.json.get('error'):
                    logging.error('Could not fetch work from queue_url=%r. '
                                  '%s', queue_url, next_item.json['error'])
                elif next_item.json and next_item.json['tasks']:
                    something_to_do = True

            if not something_to_do:
                yield timer_worker.TimerItem(poll_period)
                continue

            task_list = next_item.json['tasks']
            assert len(task_list) == 1
            task = task_list[0]
            task_id = task['task_id']
            logging.debug('Starting work item from queue_url=%r, '
                          'task=%r, workflow=%r',
                          queue_url, task, local_queue_workflow)

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
                    queue_url, task_id, message, next_index)

            payload = task['payload']
            payload.update(heartbeat=heartbeat)

            try:
                yield local_queue_workflow(**payload)
            except Exception, e:
                logging.exception('Exception while processing work from '
                                  'queue_url=%r, task=%r', queue_url, task)
                try:
                    yield heartbeat('Task failed. %s: %s' %
                                    (e.__class__.__name__, str(e)))
                except:
                    logging.exception('Failed to report error because '
                                      'heartbeat failed.')
                else:
                    if (isinstance(e, GiveUpAfterAttemptsError) and
                            task['lease_attempts'] >= e.max_attempts):
                        logging.warning(
                            'Hit max attempts on task=%r, giving up',
                            task)
                    else:
                        continue

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
                    logging.debug('Finished work item with queue_url=%r, '
                                  'task_id=%r', queue_url, task_id)


class DoPdiffQueueWorkflow(workers.WorkflowItem):
    """Runs the perceptual diff from queue parameters.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Run to run perceptual diff for.
        reference_sha1sum: Content hash of the previously good image.
        run_sha1sum: Content hash of the new image.
        heartbeat: Function to call with progress status.

    Raises:
        PdiffFailedError if the perceptual diff process failed.
    """

    def run(self, build_id=None, release_name=None, release_number=None,
            run_name=None, reference_sha1sum=None, run_sha1sum=None,
            heartbeat=None):
        output_path = tempfile.mkdtemp()
        try:
            ref_path = os.path.join(output_path, 'ref')
            run_path = os.path.join(output_path, 'run')
            diff_path = os.path.join(output_path, 'diff.png')
            log_path = os.path.join(output_path, 'log.txt')

            yield heartbeat('Fetching reference and run images')
            yield [
                release_worker.DownloadArtifactWorkflow(
                    build_id, reference_sha1sum, result_path=ref_path),
                release_worker.DownloadArtifactWorkflow(
                    build_id, run_sha1sum, result_path=run_path)
            ]

            yield heartbeat('Running perceptual diff process')
            pdiff = yield pdiff_worker.PdiffItem(
                log_path, ref_path, run_path, diff_path)

            diff_success = pdiff.returncode == 0
            max_attempts = FLAGS.pdiff_task_max_attempts

            # Check for a successful run or a known failure.
            if os.path.isfile(log_path):
                log_data = open(log_path).read()
                if 'all: 0 (0)' in log_data:
                    diff_path = None
                elif 'image widths or heights differ' in log_data:
                    # Give up immediately
                    max_attempts = 1

            yield heartbeat('Reporting diff status to server')
            yield release_worker.ReportPdiffWorkflow(
                build_id, release_name, release_number, run_name,
                diff_path, log_path, diff_success)

            if not diff_success:
                raise PdiffFailedError(
                    max_attempts,
                    'Comparison failed. returncode=%r' % pdiff.returncode)
        finally:
            shutil.rmtree(output_path, True)


class DoCaptureQueueWorkflow(workers.WorkflowItem):
    """Runs a webpage screenshot process from queue parameters.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Run to run perceptual diff for.
        url: URL of the content to screenshot.
        config_sha1sum: Content hash of the config for the new screenshot.
        baseline: Optional. When specified and True, this capture is for
            the reference baseline of the specified run, not the new capture.
        heartbeat: Function to call with progress status.

    Raises:
        CaptureFailedError if the screenshot process failed.
    """

    def run(self, build_id=None, release_name=None, release_number=None,
            run_name=None, url=None, config_sha1sum=None, baseline=None,
            heartbeat=None):
        output_path = tempfile.mkdtemp()
        try:
            image_path = os.path.join(output_path, 'capture.png')
            log_path = os.path.join(output_path, 'log.txt')
            config_path = os.path.join(output_path, 'config.json')
            capture_success = False
            failure_reason = None

            yield heartbeat('Fetching webpage capture config')
            yield release_worker.DownloadArtifactWorkflow(
                build_id, config_sha1sum, result_path=config_path)

            yield heartbeat('Running webpage capture process')
            try:
                capture = yield capture_worker.CaptureItem(
                    log_path, config_path, image_path)
            except process_worker.TimeoutError, e:
                failure_reason = str(e)
            else:
                capture_success = capture.returncode == 0
                failure_reason = 'returncode=%s' % capture.returncode

            # Don't upload bad captures, but always upload the error log.
            if not capture_success:
                image_path = None

            yield heartbeat('Reporting capture status to server')

            yield release_worker.ReportRunWorkflow(
                build_id, release_name, release_number, run_name,
                image_path=image_path, log_path=log_path, baseline=baseline)

            if not capture_success:
                raise CaptureFailedError(
                    FLAGS.capture_task_max_attempts,
                    failure_reason)
        finally:
            shutil.rmtree(output_path, True)


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    if FLAGS.queue_server_prefix:
        capture_queue_url = '%s/%s' % (
            FLAGS.queue_server_prefix, constants.CAPTURE_QUEUE_NAME)

        for i in xrange(FLAGS.capture_threads):
            item = RemoteQueueWorkflow(
                capture_queue_url,
                DoCaptureQueueWorkflow,
                poll_period=FLAGS.queue_poll_seconds)
            item.root = True
            coordinator.input_queue.put(item)

        pdiff_queue_url = '%s/%s' % (
            FLAGS.queue_server_prefix, constants.PDIFF_QUEUE_NAME)

        for i in xrange(FLAGS.pdiff_threads):
            item = RemoteQueueWorkflow(
                pdiff_queue_url,
                DoPdiffQueueWorkflow,
                poll_period=FLAGS.queue_poll_seconds)
            item.root = True
            coordinator.input_queue.put(item)
