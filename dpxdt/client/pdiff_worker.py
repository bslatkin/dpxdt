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

"""Background worker that does perceptual diffs, possibly from a queue."""

import Queue
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib2

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt import constants
import process_worker
import queue_worker
import release_worker
import workers


gflags.DEFINE_integer(
    'pdiff_task_max_attempts', 3,
    'Maximum number of attempts for processing a pdiff task.')

gflags.DEFINE_integer(
    'pdiff_threads', 1, 'Number of perceptual diff threads to run')

gflags.DEFINE_integer(
    'pdiff_timeout', 60,
    'Seconds until we should give up on a pdiff sub-process and try again.')


class PdiffFailedError(queue_worker.GiveUpAfterAttemptsError):
    """Running a perceptual diff failed for some reason."""


class PdiffItem(process_worker.ProcessItem):
    """Work item for doing perceptual diffs using pdiff."""

    def __init__(self, log_path, ref_path, run_path, output_path):
        """Initializer.

        Args:
            log_path: Where to write the verbose logging output.
            ref_path: Path to reference screenshot to diff.
            run_path: Path to the most recent run screenshot to diff.
            output_path: Where the diff image should be written, if any.
        """
        process_worker.ProcessItem.__init__(
            self, log_path, timeout_seconds=FLAGS.pdiff_timeout)
        self.ref_path = ref_path
        self.run_path = run_path
        self.output_path = output_path


class PdiffThread(process_worker.ProcessThread):
    """Worker thread that runs pdiff."""

    def get_args(self, item):
        # Method from http://www.imagemagick.org/Usage/compare/
        return [
            'compare',
            '-verbose',
            '-metric',
            'RMSE',
            '-highlight-color',
            'Red',
            '-compose',
            'Src',
            item.ref_path,
            item.run_path,
            item.output_path,
        ]


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
            pdiff = yield PdiffItem(log_path, ref_path, run_path, diff_path)

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


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    assert FLAGS.pdiff_threads > 0
    assert FLAGS.queue_server_prefix

    pdiff_queue = Queue.Queue()
    coordinator.register(PdiffItem, pdiff_queue)
    for i in xrange(FLAGS.pdiff_threads):
        coordinator.worker_threads.append(
            PdiffThread(pdiff_queue, coordinator.input_queue))

    item = queue_worker.RemoteQueueWorkflow(
        constants.PDIFF_QUEUE_NAME,
        DoPdiffQueueWorkflow,
        max_tasks=FLAGS.pdiff_threads)
    item.root = True
    coordinator.input_queue.put(item)
