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
import heapq
import logging
import time

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import workers


class TimerItem(workers.WorkItem):
    """Work item for waiting some period of time before returning."""

    def __init__(self, delay_seconds):
        workers.WorkItem.__init__(self)
        self.delay_seconds = delay_seconds
        self.ready_time = time.time() + delay_seconds


class TimerThread(workers.WorkerThread):
    """"Worker thread that tracks many timers."""

    def __init__(self, *args):
        """Initializer."""
        workers.WorkerThread.__init__(self, *args)
        self.timers = []

    def handle_nothing(self):
        now = time.time()
        while self.timers:
            ready_time, _ = self.timers[0]
            wait_time = ready_time - now
            if wait_time <= 0:
                _, item = heapq.heappop(self.timers)
                self.output_queue.put(item)
            else:
                # Wait for new work up to the point that the earliest
                # timer is ready to fire.
                self.polltime = wait_time
                return

        # Nothing to do, use the default poll time.
        self.polltime = FLAGS.polltime

    def handle_item(self, item):
        heapq.heappush(self.timers, (item.ready_time, item))
        self.handle_nothing()


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    timer_queue = Queue.Queue()
    coordinator.register(TimerItem, timer_queue)
    coordinator.worker_threads.append(
        TimerThread(timer_queue, coordinator.input_queue))
