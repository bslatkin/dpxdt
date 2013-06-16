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
    'capture_threads', 1, 'Number of website screenshot threads to run')

gflags.DEFINE_string(
    'phantomjs_binary', None, 'Path to the phantomjs binary')

gflags.DEFINE_string(
    'phantomjs_script', None,
    'Path to the script that drives the phantomjs process')


class CaptureItem(workers.ProcessItem):
    """Work item for capturing a website screenshot using PhantomJs."""

    def __init__(self, log_path, config_path, output_path):
        """Initializer.

        Args:
            log_path: Where to write the verbose logging output.
            config_path: Path to the screenshot config file to pass
                to PhantomJs.
            output_path: Where the output screenshot should be written.
        """
        workers.ProcessItem.__init__(self, log_path)
        self.config_path = config_path
        self.output_path = output_path


class CaptureThread(workers.ProcessThread):
    """Worker thread that runs PhantomJs."""

    def get_args(self, item):
        return [
            FLAGS.phantomjs_binary,
            '--disk-cache=false',
            '--debug=true',
            FLAGS.phantomjs_script,
            item.config_path,
            item.output_path,
        ]


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    assert FLAGS.phantomjs_binary
    assert FLAGS.phantomjs_script
    assert FLAGS.capture_threads > 0
    capture_queue = Queue.Queue()
    coordinator.register(CaptureItem, capture_queue)
    for i in xrange(FLAGS.capture_threads):
        coordinator.worker_threads.append(
            CaptureThread(capture_queue, coordinator.input_queue))
