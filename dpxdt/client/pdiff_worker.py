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
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib2
import re

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
    'pdiff_task_max_attempts', 3,
    'Maximum number of attempts for processing a pdiff task.')

gflags.DEFINE_integer(
    'pdiff_wait_seconds', 3,
    'Wait this many seconds between repeated invocations of pdiff '
    'subprocesses. Can be used to spread out load on the server.')

gflags.DEFINE_string(
    'pdiff_compare_binary', 'compare',
    'Path to the compare binary used for generating perceptual diffs.')

gflags.DEFINE_string(
    'pdiff_composite_binary', 'composite',
    'Path to the composite binary used for resizing images.')

gflags.DEFINE_integer(
    'pdiff_threads', 1, 'Number of perceptual diff threads to run')

gflags.DEFINE_integer(
    'pdiff_timeout', 60,
    'Seconds until we should give up on a pdiff sub-process and try again.')

DIFF_REGEX = re.compile(".*all:.*\(([0-9e\-\.]*)\).*")


class PdiffFailedError(queue_worker.GiveUpAfterAttemptsError):
    """Running a perceptual diff failed for some reason."""


class ResizeWorkflow(process_worker.ProcessWorkflow):
    """Workflow for making images to be diffed the same size."""

    def __init__(self, log_path, ref_path, run_path, resized_ref_path):
        """Initializer.

        Args:
            log_path: Where to write the verbose logging output.
            ref_path: Path to reference screenshot to diff.
            run_path: Path to the most recent run screenshot to diff.
            resized_ref_path: Where the resized ref image should be written.
        """
        process_worker.ProcessWorkflow.__init__(
            self, log_path, timeout_seconds=FLAGS.pdiff_timeout)
        self.ref_path = ref_path
        self.run_path = run_path
        self.resized_ref_path = resized_ref_path

    def get_args(self):
        return [
            FLAGS.pdiff_composite_binary,
            '-compose',
            'src',
            '-gravity',
            'NorthWest',
            self.ref_path,
            self.run_path,
            self.resized_ref_path,
        ]


class PdiffWorkflow(process_worker.ProcessWorkflow):
    """Workflow for doing perceptual diffs using pdiff."""

    def __init__(self, log_path, ref_path, run_path, output_path):
        """Initializer.

        Args:
            log_path: Where to write the verbose logging output.
            ref_path: Path to reference screenshot to diff.
            run_path: Path to the most recent run screenshot to diff.
            output_path: Where the diff image should be written, if any.
        """
        process_worker.ProcessWorkflow.__init__(
            self, log_path, timeout_seconds=FLAGS.pdiff_timeout)
        self.ref_path = ref_path
        self.run_path = run_path
        self.output_path = output_path

    def get_args(self):
        # Method from http://www.imagemagick.org/Usage/compare/
        return [
            FLAGS.pdiff_compare_binary,
            '-verbose',
            '-metric',
            'RMSE',
            '-highlight-color',
            'Red',
            '-compose',
            'Src',
            self.ref_path,
            self.run_path,
            self.output_path,
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
            ref_resized_path = os.path.join(output_path, 'ref_resized')
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

            max_attempts = FLAGS.pdiff_task_max_attempts

            yield heartbeat('Resizing reference image')
            returncode = yield ResizeWorkflow(
                log_path, ref_path, run_path, ref_resized_path)
            if returncode != 0:
                raise PdiffFailedError(
                    max_attempts,
                    'Could not resize reference image to size of new image')

            yield heartbeat('Running perceptual diff process')
            returncode = yield PdiffWorkflow(
                log_path, ref_resized_path, run_path, diff_path)

            # ImageMagick returns 1 if the images are different and 0 if
            # they are the same, so the return code is a bad judge of
            # successfully running the diff command. Instead we need to check
            # the output text.
            diff_failed = True

            # Check for a successful run or a known failure.
            distortion = None
            if os.path.isfile(log_path):
                log_data = open(log_path).read()
                if 'all: 0 (0)' in log_data:
                    diff_path = None
                    diff_failed = False
                elif 'image widths or heights differ' in log_data:
                    # Give up immediately
                    max_attempts = 1
                else:
                    # Try to find the image magic normalized root square
                    # mean and grab the first one.
                    r = DIFF_REGEX.findall(log_data)
                    if len(r) > 0:
                        diff_failed = False
                        distortion = r[0]

            yield heartbeat('Reporting diff result to server')
            yield release_worker.ReportPdiffWorkflow(
                build_id, release_name, release_number, run_name,
                diff_path, log_path, diff_failed, distortion)

            if diff_failed:
                raise PdiffFailedError(
                    max_attempts,
                    'Comparison failed. returncode=%r' % returncode)
        finally:
            shutil.rmtree(output_path, True)


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    assert FLAGS.pdiff_threads > 0
    assert FLAGS.queue_server_prefix

    item = queue_worker.RemoteQueueWorkflow(
        constants.PDIFF_QUEUE_NAME,
        DoPdiffQueueWorkflow,
        max_tasks=FLAGS.pdiff_threads,
        wait_seconds=FLAGS.pdiff_wait_seconds)
    item.root = True
    coordinator.input_queue.put(item)
