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
from dpxdt.client import workers
from dpxdt.server import db
from dpxdt.server import work_queue
from dpxdt.tools import run_server

# Test-only modules
import test_utils


# Will be set by one-time setUp
server_thread = None


TEST_QUEUE = 'test-queue'


def setUpModule():
    """Sets up the environment for testing."""
    global server_thread
    server_thread = test_utils.start_server()


class TestQueueWorkflow(workers.WorkflowItem):
    def run(self, foo=None, bar=None, baz=None, heartbeat=None):
        yield heartbeat('Inside the workflow!')


class RemoteQueueWorkflowTest(unittest.TestCase):
    """Tests for the RemoteQueueWorkflow."""

    def setUp(self):
        """Sets up the test harness."""
        FLAGS.queue_idle_poll_seconds = 0.01
        FLAGS.queue_busy_poll_seconds = 0.01
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

    def testLeaseAndFinish(self):
        """Tests leasing tasks and finishing them."""
        task_ids = []
        for i in xrange(10):
            next_id = work_queue.add(
                TEST_QUEUE,
                payload={'foo': i, 'bar': 5.5, 'baz': 'banana'})
            task_ids.append(next_id)
        db.session.commit()

        item = queue_worker.RemoteQueueWorkflow(
            TEST_QUEUE,
            TestQueueWorkflow,
            max_tasks=1,
            wait_seconds=0.01)
        item.root = True
        self.coordinator.input_queue.put(item)
        time.sleep(1)
        item.stop()
        self.coordinator.wait_one()

        for task_id in task_ids:
            found = work_queue.WorkQueue.query.get((task_id, TEST_QUEUE))
            self.assertEquals(work_queue.WorkQueue.DONE, found.status)


def main(argv):
    logging.getLogger().setLevel(logging.DEBUG)
    argv = FLAGS(argv)
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
