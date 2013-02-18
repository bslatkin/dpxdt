#!/usr/bin/env python
# Copyright 2013 Brett Slatkin

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TODO"""

import Queue
import logging
import sys


# Local Libraries
import gflags
import workers


FLAGS = gflags.FLAGS


class PdiffWorkflow(workers.WorkflowItem):
  """TODO"""

  def run(self):
    ref = yield workers.CaptureItem(
        '/tmp/test_ref.log',
        '/Users/bslatkin/projects/hostedpdiff/client/config.js',
        '/tmp/test_ref.png')
    run = yield workers.CaptureItem(
        '/tmp/test_run.log',
        '/Users/bslatkin/projects/hostedpdiff/client/config.js',
        '/tmp/test_run.png')
    diff = yield workers.DiffItem(
        '/tmp/test_diff.log', ref.output_path, run.output_path,
        '/tmp/test_diff.png')
    # If the diff has an error and the output file is present, then
    # we found a pixel diff. Otherwise if there is no error there is no diff.


def main(argv):
  try:
    argv = FLAGS(argv)
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  logging.getLogger().setLevel(logging.DEBUG)

  capture_queue = Queue.Queue()
  diff_queue = Queue.Queue()
  workflow_queue = Queue.Queue()
  complete_queue = Queue.Queue()

  coordinator = workers.WorkflowThread(workflow_queue, complete_queue)
  coordinator.register(workers.CaptureItem, capture_queue)
  coordinator.register(workers.DiffItem, diff_queue)

  worker_threads = [
    coordinator,
    workers.CaptureThread(capture_queue, workflow_queue),
    workers.DiffThread(diff_queue, workflow_queue),
  ]
  for thread in worker_threads:
    thread.start()

  # Add in pdiff workers for new jobs
  # Retire them on error

  item = PdiffWorkflow()
  workflow_queue.put(item)
  result = complete_queue.get()
  if result.error:
    raise result.error[0], result.error[1], result.error[2]


if __name__ == '__main__':
  main(sys.argv)
