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

"""Workers for driving screen captures, perceptual diffs, and related work."""

import Queue
import logging
import subprocess
import time

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
import workers


class Error(Exception):
    """Base class for exceptions in this module."""

class TimeoutError(Exception):
    """Subprocess has taken too long to complete and was terminated."""


class ProcessItem(workers.WorkItem):
    """Work item that is handled by running a subprocess."""

    def __init__(self, log_path, timeout_seconds=30):
        """Initializer.

        Args:
            log_path: Path to where output from this subprocess should be
                written.
            timeout_seconds: How long before the process should be force
                killed.
        """
        workers.WorkItem.__init__(self)
        self.log_path = log_path
        self.timeout_seconds = timeout_seconds
        self.return_code = None


class ProcessThread(workers.WorkerThread):
    """Worker thread that runs subprocesses."""

    def get_args(self, item):
        raise NotImplemented

    def handle_item(self, item):
        start_time = time.time()
        with open(item.log_path, 'w') as output_file:
            args = self.get_args(item)
            logging.debug('%s item=%r Running subprocess: %r',
                          self.worker_name, item, args)
            try:
                process = subprocess.Popen(
                    args,
                    stderr=subprocess.STDOUT,
                    stdout=output_file,
                    close_fds=True)
            except:
                logging.error('%s item=%r Failed to run subprocess: %r',
                              self.worker_name, item, args)
                raise

            while True:
                process.poll()
                if process.returncode is None:
                    now = time.time()
                    run_time = now - start_time
                    if run_time > item.timeout_seconds or self.interrupted:
                        process.kill()
                        raise TimeoutError(
                            'Sent SIGKILL to item=%r, pid=%s, run_time=%s' %
                            (item, process.pid, run_time))

                    time.sleep(FLAGS.polltime)
                    continue

                item.returncode = process.returncode

                return item
