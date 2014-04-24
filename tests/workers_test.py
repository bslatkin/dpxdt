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


class RootWaitAllWorkflow(workers.WorkflowItem):
    def run(self, child_count):
        wait_all = [EchoItem(i) for i in xrange(child_count)]
        output = yield wait_all
        raise workers.Return(sum(x.output_number for x in output))


class RootWaitAnyWorkflow(workers.WorkflowItem):
    def run(self):
        output = yield workers.WaitAny([
            EchoItem(10),
            EchoChild(42),
            EchoItem(2),
            EchoItem(25),
        ])
        # At least one EchoItem will be done. We don't know exactly because
        # the jobs WorkflowItems in WaitAny are inserted into a dictionary
        # so their completion ordering is non-deterministic.
        assert len([x for x in output if x.done]) >= 1
        # The EchoChild will not be ready yet.
        assert not output[1].done

        yield timer_worker.TimerItem(2)

        results = yield output
        # Now everything will be done.
        assert len([x for x in output if x.done]) >= 1
        assert results[0].done and results[0].output_number == 10
        assert results[1] == 42
        assert results[2].done and results[2].output_number == 2
        assert results[3].done and results[3].output_number == 25

        raise workers.Return('Donezo')


class RootWaitAnyExceptionWorkflow(workers.WorkflowItem):
    def run(self):
        output = yield workers.WaitAny([
            EchoChild(42, should_die=True),
            EchoItem(10),
            EchoItem(33),
        ])
        assert len([x for x in output if x.done]) == 2
        assert not output[0].done
        assert output[1].done and output[1].output_number == 10
        assert output[2].done and output[2].output_number == 33

        yield timer_worker.TimerItem(2)

        try:
            yield output
        except Exception, e:
            raise workers.Return(str(e))
        else:
            assert False, 'Should have raised'


class FireAndForgetEchoItem(EchoItem):
    fire_and_forget = True


class RootFireAndForgetWorkflow(workers.WorkflowItem):
    def run(self):
        job1 = FireAndForgetEchoItem(10)
        result = yield job1
        print result
        assert result is job1
        assert not result.done

        result = yield EchoItem(25)
        assert result.done
        assert result.output_number == 25

        job2 = EchoItem(30)
        job2.fire_and_forget = True
        result = yield job2
        assert result is job2
        assert not result.done

        job3 = FireAndForgetEchoItem(66)
        job3.fire_and_forget = False
        result = yield job3
        assert result is job3
        assert result.done
        assert result.output_number == 66

        job4 = EchoChild(22)
        job4.fire_and_forget = True
        result = yield job4
        assert result is job4
        assert not result.done

        yield timer_worker.TimerItem(2)
        assert job1.done
        assert job1.output_number == 10
        assert job2.done
        assert job2.output_number == 30
        assert job4.done
        assert job4.result == 22

        raise workers.Return('Okay')


class RootFireAndForgetExceptionWorkflow(workers.WorkflowItem):
    def run(self):
        job = EchoChild(99, should_die=True)
        job.fire_and_forget = True
        result = yield job
        assert result is job
        assert not result.done
        assert not result.error

        result = yield EchoItem(25)
        assert result.done
        assert result.output_number == 25

        yield timer_worker.TimerItem(2)
        assert job.done
        assert str(job.error[1]) == 'Dying on 99'

        raise workers.Return('No fire and forget error')


class RootWaitAnyFireAndForget(workers.WorkflowItem):
    def run(self):
        output = yield workers.WaitAny([
            FireAndForgetEchoItem(22),
            EchoItem(14),
            EchoChild(98),
        ])
        assert output[0].done
        assert output[1].done
        assert not output[2].done

        # Yielding here will let the next pending WorkflowItem to run,
        # causing output #3 to finish.
        result = yield output
        assert result[2] == 98

        raise workers.Return('All done')


class RootWaitAllFireAndForget(workers.WorkflowItem):
    def run(self):
        output = yield [
            FireAndForgetEchoItem(22),
            EchoItem(14),
            EchoChild(98),
        ]
        assert output[0].done
        assert output[1].done
        assert output[2] == 98

        raise workers.Return('Waited for all of them')


class WorkflowThreadTest(unittest.TestCase):
    """Tests for the WorkflowThread worker."""

    def setUp(self):
        """Sets up the test harness."""
        FLAGS.fetch_frequency = 100
        FLAGS.polltime = 0.01
        self.coordinator = workers.get_coordinator()

        self.echo_queue = Queue.Queue()
        self.coordinator.register(EchoItem, self.echo_queue)
        self.coordinator.register(FireAndForgetEchoItem, self.echo_queue)
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
        # Nothing should be pending in the coordinator
        self.assertEquals(0, len(self.coordinator.pending))

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

    def testWaitAll(self):
        """Tests waiting on all items in a list of work."""
        work = RootWaitAllWorkflow(4)
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals(6, work.result)

    def testWaitAny(self):
        """Tests using the WaitAny class."""
        work = RootWaitAnyWorkflow()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals('Donezo', work.result)

    def testWaitAnyException(self):
        """Tests using the WaitAny class when an exception is raised."""
        work = RootWaitAnyExceptionWorkflow()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals('Dying on 42', work.result)

    def testFireAndForget(self):
        """Tests running fire-and-forget WorkItems."""
        work = RootFireAndForgetWorkflow()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals('Okay', work.result)

    def testFireAndForgetException(self):
        """Tests that exceptions from fire-and-forget WorkItems are ignored."""
        work = RootFireAndForgetExceptionWorkflow()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals('No fire and forget error', work.result)

    def testWaitAnyFireAndForget(self):
        """Tests wait any with a mix of blocking and non-blocking items."""
        work = RootWaitAnyFireAndForget()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals('All done', work.result)

    def testWaitAllFireAndForget(self):
        """Tests wait all with a mix of blocking and non-blocking items."""
        work = RootWaitAllFireAndForget()
        work.root = True
        self.coordinator.input_queue.put(work)
        finished = self.coordinator.output_queue.get()
        self.assertTrue(work is finished)
        finished.check_result()
        self.assertEquals('Waited for all of them', work.result)


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
