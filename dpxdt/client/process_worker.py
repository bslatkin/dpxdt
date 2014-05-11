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
from dpxdt.client import timer_worker
from dpxdt.client import workers


class Error(Exception):
    """Base class for exceptions in this module."""

class TimeoutError(Exception):
    """Subprocess has taken too long to complete and was terminated."""


class ProcessWorkflow(workers.WorkflowItem):
    """Workflow that runs a subprocess.

    Args:
        log_path: Path to where output from this subprocess should be written.
        timeout_seconds: How long before the process should be force killed.

    Returns:
        The return code of the subprocess.
    """

    def get_args(self):
        """Return the arguments for running the subprocess."""
        raise NotImplemented

    def run(self, log_path, timeout_seconds=30):
        start_time = time.time()
        with open(log_path, 'a') as output_file:
            args = self.get_args()
            logging.info('item=%r Running subprocess: %r', self, args)
            try:
                process = subprocess.Popen(
                    args,
                    stderr=subprocess.STDOUT,
                    stdout=output_file,
                    close_fds=True)
            except:
                logging.error('item=%r Failed to run subprocess: %r',
                              self, args)
                raise

            while True:
                logging.info('item=%r Polling pid=%r', self, process.pid)
                # NOTE: Use undocumented polling method to work around a
                # bug in subprocess for handling defunct zombie processes:
                # http://bugs.python.org/issue2475
                process._internal_poll(_deadstate=127)
                if process.returncode is not None:
                    logging.info(
                        'item=%r Subprocess finished pid=%r, returncode=%r',
                        self, process.pid, process.returncode)
                    raise workers.Return(process.returncode)

                now = time.time()
                run_time = now - start_time
                if run_time > timeout_seconds:
                    logging.info('item=%r Subprocess timed out pid=%r',
                                 self, process.pid)
                    process.kill()
                    raise TimeoutError(
                        'Sent SIGKILL to item=%r, pid=%s, run_time=%s' %
                        (self, process.pid, run_time))

                yield timer_worker.TimerItem(FLAGS.polltime)
