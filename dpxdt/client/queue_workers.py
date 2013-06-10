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
import pdiff_worker
import release_worker
import site_diff
import workers


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

class HeartbeatError(Error):
    """Reporting the status of a task in progress failed for some reason."""

class PdiffFailedError(Error):
    """Running a perceptual diff failed for some reason."""

class CaptureFailedError(Error):
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
        call = yield workers.FetchItem(
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

    def run(self, queue_url, local_queue_workflow, poll_period=60):
        while True:
            try:
                next_item = yield workers.FetchItem(
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
                yield workers.TimerItem(poll_period)
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
                    continue

            try:
                finish_item = yield workers.FetchItem(
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
                    reference_sha1sum, result_path=ref_path),
                release_worker.DownloadArtifactWorkflow(
                    run_sha1sum, result_path=run_path)
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


class DoCaptureQueueWorkflow(workers.WorkflowItem):
    """Runs a webpage screenshot process from queue parameters.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Run to run perceptual diff for.
        config_sha1sum: Content hash of the config for the new screenshot.
        heartbeat: Function to call with progress status.

    Raises:
        CaptureFailedError if the screenshot process failed.
    """

    def run(self, build_id=None, release_name=None, release_number=None,
            run_name=None, config_sha1sum=None, heartbeat=None):
        output_path = tempfile.mkdtemp()
        try:
            image_path = os.path.join(output_path, 'capture')
            log_path = os.path.join(output_path, 'log')
            config_path = os.path.join(output_path, 'config')

            yield heartbeat('Fetching webpage capture config')
            yield release_worker.DownloadArtifactWorkflow(
                config_sha1sum, result_path=config_path)

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


class DoSiteDiffQueueWorkflow(workers.WorkflowItem):
    """Runs a site diff from queue parameters.

    Args:
        build_Id: ID of the build.
        start_url: URL to begin the scan.
        ignore_prefixes: List of prefixes to ignore during the scan.
        heartbeat: Fucntion to call with progress status.
    """

    def run(self, build_id=None, start_url=None, ignore_prefixes=None,
            heartbeat=None):
        output_path = tempfile.mkdtemp()
        try:
            yield site_diff.SiteDiff(
                start_url,
                output_path,
                ignore_prefixes,
                upload_build_id=build_id,
                heartbeat=heartbeat)
        finally:
            shutil.rmtree(output_path, True)


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    # TODO: Add a flag to support up to N parallel queue workers.

    if FLAGS.queue_server_prefix:
        capture_queue_url = '%s/%s' % (
            FLAGS.queue_server_prefix, constants.CAPTURE_QUEUE_NAME)
        item = RemoteQueueWorkflow(
            capture_queue_url,
            DoCaptureQueueWorkflow,
            poll_period=FLAGS.queue_poll_seconds)
        item.root = True
        coordinator.input_queue.put(item)

        pdiff_queue_url = '%s/%s' % (
            FLAGS.queue_server_prefix, constants.PDIFF_QUEUE_NAME)
        item = RemoteQueueWorkflow(
            pdiff_queue_url,
            DoPdiffQueueWorkflow,
            poll_period=FLAGS.queue_poll_seconds)
        item.root = True
        coordinator.input_queue.put(item)

        site_diff_queue_url = '%s/%s' % (
            FLAGS.queue_server_prefix, constants.SITE_DIFF_QUEUE_NAME)
        item = RemoteQueueWorkflow(
            site_diff_queue_url,
            DoSiteDiffQueueWorkflow,
            poll_period=FLAGS.queue_poll_seconds)
        item.root = True
        coordinator.input_queue.put(item)
