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

"""Tests for the workers module.

To run:

PYTHONPATH=./lib:$PYTHONPATH \
./tests/workers_test.py \
"""

import Queue
import logging
import sys
import unittest

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import workers


class EchoThread(workers.WorkerThread):
    def handle_item(self, item):
        if item.should_die:
            raise Exception('Dying on %d' % item.input_number)
        item.output_number = item.input_number
        return item


class EchoItem(workers.WorkItem):
    def __init__(self, number, should_die=False):
        workers.WorkItem.__init__(self)
        self.input_number = number
        self.output_number = None
        self.should_die = should_die


class EchoChild(workers.WorkflowItem):
    def run(self, number, should_die=False):
        item = yield EchoItem(number, should_die=should_die)
        self.result = item.output_number


class RootWorkflow(workers.WorkflowItem):
    def run(self, child_count, die_on=-1):
        total = 0
        for i in xrange(child_count):
            workflow = yield EchoChild(i, should_die=(die_on == i))
            assert workflow.result == i
            total += workflow.result
        self.result = total


class WorkflowThreadTest(unittest.TestCase):
    """Tests for the WorkflowThread worker."""

    def setUp(self):
        """Sets up the test harness."""
        FLAGS.fetch_frequency = 100
        FLAGS.polltime = 0.01
        self.coordinator = workers.GetCoordinator()

    def tearDown(self):
        """Cleans up the test harness."""
        self.coordinator.stop()

    def testMultiLevelWorkflow(self):
        """Tests a multi-level workflow."""
        echo_queue = Queue.Queue()
        self.coordinator.register(EchoItem, echo_queue)
        self.coordinator.worker_threads.append(
            EchoThread(echo_queue, self.coordinator.input_queue))
        self.coordinator.start()

        work = RootWorkflow(5)
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()

        self.assertTrue(work is finished)
        finished.check_result()    # Did not raise
        self.assertEquals(4 + 3 + 2 + 1 + 0, work.result)

    def testMultiLevelWorkflowException(self):
        """Tests when a child of a child raises an exception."""
        echo_queue = Queue.Queue()
        self.coordinator.register(EchoItem, echo_queue)
        self.coordinator.worker_threads.append(
            EchoThread(echo_queue, self.coordinator.input_queue))
        self.coordinator.start()

        work = RootWorkflow(5, die_on=3)
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()

        self.assertTrue(work is finished)
        try:
            finished.check_result()
        except Exception, e:
            self.assertEquals('Dying on 3', str(e))


def main(argv):
    logging.getLogger().setLevel(logging.DEBUG)
    argv = FLAGS(argv)
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
