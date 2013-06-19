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
import subprocess
import sys
import threading
import time
import urllib2

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
import workers


gflags.DEFINE_integer(
    'pdiff_threads', 1, 'Number of perceptual diff threads to run')

gflags.DEFINE_integer(
    'pdiff_timeout', 60,
    'Seconds until we should give up on a pdiff sub-process and try again.')



class PdiffItem(workers.ProcessItem):
    """Work item for doing perceptual diffs using pdiff."""

    def __init__(self, log_path, ref_path, run_path, output_path):
        """Initializer.

        Args:
            log_path: Where to write the verbose logging output.
            ref_path: Path to reference screenshot to diff.
            run_path: Path to the most recent run screenshot to diff.
            output_path: Where the diff image should be written, if any.
        """
        workers.ProcessItem.__init__(
            self, log_path, timeout_seconds=FLAGS.pdiff_timeout)
        self.ref_path = ref_path
        self.run_path = run_path
        self.output_path = output_path


class PdiffThread(workers.ProcessThread):
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


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    assert FLAGS.pdiff_threads > 0
    pdiff_queue = Queue.Queue()
    coordinator.register(PdiffItem, pdiff_queue)
    for i in xrange(FLAGS.pdiff_threads):
        coordinator.worker_threads.append(
            PdiffThread(pdiff_queue, coordinator.input_queue))
