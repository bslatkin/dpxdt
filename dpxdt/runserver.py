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

"""Runs the dpxdt API server, optionally with local queue workers.


Example usage with local workers:

PYTHONPATH=./lib:$PYTHONPATH \
./dpxdt/runserver.py \
    --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
    --phantomjs_script=path/to/client/capture.js \
    --pdiff_binary=path/to/pdiff/perceptualdiff \
    --local_queue_workers \
    --pdiff_queue_url=http://localhost:5000/api/work_queue/run-pdiff \
    --capture_queue_url=http://localhost:5000/api/work_queue/run-capture


Example usage just as an API server:

PYTHONPATH=./lib:$PYTHONPATH \
./dpxdt/runserver.py

"""

import logging
import sys

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from client import capture_worker
from client import pdiff_worker
from client import queue_workers
from client import workers
import server


gflags.DEFINE_bool(
    'local_queue_workers', False,
    'When true, run queue worker threads locally in the same process '
    'as the server.')

gflags.DEFINE_bool(
    'verbose', False,
    'When set, do verbose logging output.')


def run_workers():
    coordinator = workers.GetCoordinator()
    capture_worker.register(coordinator)
    pdiff_worker.register(coordinator)
    queue_workers.register(coordinator)
    coordinator.start()
    logging.debug('Workers started')


def main(argv):
    try:
        argv = FLAGS(argv)
    except gflags.FlagsError, e:
        print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)

    if FLAGS.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if FLAGS.local_queue_workers:
        run_workers()

    server.app.run(debug=True)


if __name__ == '__main__':
    main(sys.argv)
