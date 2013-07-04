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

"""Tests for the workers module."""

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
from dpxdt.client import workers
from dpxdt.client import timer_worker


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
        raise workers.Return(item.output_number)


class RootWorkflow(workers.WorkflowItem):
    def run(self, child_count, die_on=-1):
        total = 0
        for i in xrange(child_count):
            number = yield EchoChild(i, should_die=(die_on == i))
            assert number is i
            total += number
        self.result = total  # Don't raise to test StopIteration


class RootWaitAnyWorkflow(workers.WorkflowItem):
    def run(self):
        print 'before!'
        output = yield workers.WaitAny([
            EchoItem(10),
            EchoChild(42),
            EchoItem(2),
            EchoItem(25),
        ])
        assert len([x for x in output if x.done]) == 1
        assert output[0].done and output[0].output_number == 10
        assert not output[1].done
        assert not output[2].done
        assert not output[3].done

        yield timer_worker.TimerItem(2)

        results = yield output
        assert results[0].done and results[0].output_number == 10
        assert results[1] == 42
        assert results[2].done and results[2].output_number == 2
        assert results[3].done and results[3].output_number == 25

        raise workers.Return('Donezo')


class WorkflowThreadTest(unittest.TestCase):
    """Tests for the WorkflowThread worker."""

    def setUp(self):
        """Sets up the test harness."""
        FLAGS.fetch_frequency = 100
        FLAGS.polltime = 0.01
        self.coordinator = workers.get_coordinator()

        self.echo_queue = Queue.Queue()
        self.coordinator.register(EchoItem, self.echo_queue)
        self.coordinator.worker_threads.append(
            EchoThread(self.echo_queue, self.coordinator.input_queue))

        self.timer_queue = Queue.Queue()
        self.coordinator.register(timer_worker.TimerItem, self.timer_queue)
        self.coordinator.worker_threads.append(
            timer_worker.TimerThread(
                self.timer_queue, self.coordinator.input_queue))

        self.coordinator.start()

    def tearDown(self):
        """Cleans up the test harness."""
        self.coordinator.stop()
        self.coordinator.join()

    def testMultiLevelWorkflow(self):
        """Tests a multi-level workflow."""
        work = RootWorkflow(5)
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()

        self.assertTrue(work is finished)
        finished.check_result()    # Did not raise
        self.assertEquals(4 + 3 + 2 + 1 + 0, work.result)

    def testMultiLevelWorkflowException(self):
        """Tests when a child of a child raises an exception."""
        work = RootWorkflow(5, die_on=3)
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()

        self.assertTrue(work is finished)
        try:
            finished.check_result()
        except Exception, e:
            self.assertEquals('Dying on 3', str(e))

    def testWaitAny(self):
        """Tests using the WaitAny class."""
        work = RootWaitAnyWorkflow()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()


class TimerThreadTest(unittest.TestCase):
    """Tests for the TimerThread."""

    def setUp(self):
        """Tests setting up the test harness."""
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
