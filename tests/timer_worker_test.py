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

"""Tests for the timer_worker module."""

import Queue
import logging
import sys
import time
import unittest

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import timer_worker


class TimerThreadTest(unittest.TestCase):
    """Tests for the TimerThread."""

    def setUp(self):
        """Sets up the test harness."""
        self.timer_queue = Queue.Queue()
        self.output_queue = Queue.Queue()
        self.worker = timer_worker.TimerThread(
            self.timer_queue, self.output_queue)

    def testSimple(self):
        """Tests simple waiting."""
        self.worker.start()
        one = timer_worker.TimerItem(0.8)
        two = timer_worker.TimerItem(0.5)
        three = timer_worker.TimerItem(0.1)

        # T = 0, one = 0
        begin = time.time()
        self.timer_queue.put(one)
        time.sleep(0.2)
        # T = 0.2, one = 0.2, two = 0
        self.timer_queue.put(two)
        time.sleep(0.2)
        # T = 0.4, one = 0.4, two = 0.2
        self.timer_queue.put(three)
        time.sleep(0.2)
        # T = 0.6, one = 0.6, two = 0.4, three = 0.1 ready!
        output_three = self.output_queue.get()
        time.sleep(0.1)
        # T = 0.7, one = 0.7, two = 0.5 ready!
        output_two = self.output_queue.get()
        # T = 0.8, one = 0.8 ready!
        output_one = self.output_queue.get()
        end = time.time()

        self.assertEquals(one.delay_seconds, output_one.delay_seconds)
        self.assertEquals(two.delay_seconds, output_two.delay_seconds)
        self.assertEquals(three.delay_seconds, output_three.delay_seconds)

        elapsed = end - begin
        self.assertTrue(1.0 > elapsed > 0.7)


def main(argv):
    logging.getLogger().setLevel(logging.DEBUG)
    argv = FLAGS(argv)
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
