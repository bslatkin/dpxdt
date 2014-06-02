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

"""Background worker that screenshots URLs, possibly from a queue."""

import Queue
import json
import os
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import urllib2

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt import constants
from dpxdt.client import process_worker
from dpxdt.client import queue_worker
from dpxdt.client import release_worker
from dpxdt.client import workers


gflags.DEFINE_integer(
    'capture_threads', 5, 'Number of website screenshot threads to run')

gflags.DEFINE_integer(
    'capture_task_max_attempts', 3,
    'Maximum number of attempts for processing a capture task.')

gflags.DEFINE_integer(
    'capture_wait_seconds', 3,
    'Wait this many seconds between repeated invocations of capture '
    'subprocesses. Can be used to spread out load on the server.')

gflags.DEFINE_string(
    'phantomjs_binary', None, 'Path to the phantomjs binary')

gflags.DEFINE_string(
    'phantomjs_script', None,
    'Path to the script that drives the phantomjs process')

gflags.DEFINE_integer(
    'phantomjs_timeout', 120,
    'Seconds until giving up on a phantomjs sub-process and trying again.')



class CaptureFailedError(queue_worker.GiveUpAfterAttemptsError):
    """Capturing a webpage screenshot failed for some reason."""


class CaptureWorkflow(process_worker.ProcessWorkflow):
    """Workflow for capturing a website screenshot using PhantomJs."""

    def __init__(self, log_path, config_path, output_path):
        """Initializer.

        Args:
            log_path: Where to write the verbose logging output.
            config_path: Path to the screenshot config file to pass
                to PhantomJs.
            output_path: Where the output screenshot should be written.
        """
        process_worker.ProcessWorkflow.__init__(
            self, log_path, timeout_seconds=FLAGS.phantomjs_timeout)
        self.config_path = config_path
        self.output_path = output_path

    def get_args(self):
        return [
            FLAGS.phantomjs_binary,
            '--disk-cache=false',
            '--debug=true',
            '--ignore-ssl-errors=true',
            FLAGS.phantomjs_script,
            self.config_path,
            self.output_path,
        ]


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
            capture_failed = True
            failure_reason = None

            yield heartbeat('Fetching webpage capture config')
            yield release_worker.DownloadArtifactWorkflow(
                build_id, config_sha1sum, result_path=config_path)

            yield heartbeat('Running webpage capture process')
            try:
                returncode = yield CaptureWorkflow(
                    log_path, config_path, image_path)
            except (process_worker.TimeoutError, OSError), e:
                failure_reason = str(e)
            else:
                capture_failed = returncode != 0
                failure_reason = 'returncode=%s' % returncode

            # Don't upload bad captures, but always upload the error log.
            if capture_failed:
                image_path = None

            yield heartbeat('Reporting capture status to server')
            yield release_worker.ReportRunWorkflow(
                build_id, release_name, release_number, run_name,
                image_path=image_path, log_path=log_path, baseline=baseline,
                run_failed=capture_failed)

            if capture_failed:
                raise CaptureFailedError(
                    FLAGS.capture_task_max_attempts,
                    failure_reason)
        finally:
            shutil.rmtree(output_path, True)


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    assert FLAGS.phantomjs_binary
    assert FLAGS.phantomjs_script
    assert FLAGS.capture_threads > 0
    assert FLAGS.queue_server_prefix

    item = queue_worker.RemoteQueueWorkflow(
        constants.CAPTURE_QUEUE_NAME,
        DoCaptureQueueWorkflow,
        max_tasks=FLAGS.capture_threads,
        wait_seconds=FLAGS.capture_wait_seconds)
    item.root = True
    coordinator.input_queue.put(item)
