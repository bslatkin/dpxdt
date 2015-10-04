#!/usr/bin/env python
# Copyright 2015 Brett Slatkin
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

"""Tests for the queue_worker module."""

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
from dpxdt.client import queue_worker
from dpxdt.client import timer_worker


class RemoteQueueWorkflowTest(unittest.TestCase):
    """Tests for the RemoteQueueWorkflow."""

    def setUp(self):
        """Sets up the test harness."""
        FLAGS.fetch_frequency = 100
        FLAGS.fetch_threads = 1
        FLAGS.polltime = 0.01
        self.coordinator = workers.get_coordinator()
        fetch_worker.register(self.coordinator)
        timer_worker.register(self.coordinator)
        self.coordinator.start()

    def tearDown(self):
        """Cleans up the test harness."""
        self.coordinator.stop()
        self.coordinator.join()
        # Nothing should be pending in the coordinator
        self.assertEquals(0, len(self.coordinator.pending))

    def testQueue(self):
        """TODO"""
        self.fail()


def main(argv):
    logging.getLogger().setLevel(logging.DEBUG)
    argv = FLAGS(argv)
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
