#!/usr/bin/env python
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the fetch_worker module."""

import Queue
import logging
import sys
import time
import unittest

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import fetch_worker


class FetchWorkerTest(unittest.TestCase):
    """Tests for the FetchWorker."""

    def setUp(self):
        """Sets up the test harness."""
        self.input_queue = Queue.Queue()
        self.output_queue = Queue.Queue()
        self.worker = fetch_worker.FetchThread(self.input_queue, self.output_queue)

    def testForbiddenScheme(self):
        """Tests that some schemes are not allowed."""
        self.worker.start()
        self.input_queue.put(fetch_worker.FetchItem('file:///etc/passwd'))
        time.sleep(0.1)
        result = self.output_queue.get()
        self.assertEquals(403, result.status_code)


def main(argv):
    logging.getLogger().setLevel(logging.DEBUG)
    argv = FLAGS(argv)
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
