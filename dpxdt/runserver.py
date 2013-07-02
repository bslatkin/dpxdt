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

"""Runs the dpxdt API server, optionally with local queue workers."""

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
from server import models


gflags.DEFINE_bool(
    'local_queue_workers', False,
    'When true, run queue worker threads locally in the same process '
    'as the server.')

gflags.DEFINE_bool('reload_code', False,
    'Reload code on every request. Should only be used in local development.')

gflags.DEFINE_bool('ignore_auth', False,
    'Ignore any need for authentication for API and frontend accesses. You '
    'should only do this for local development!')

gflags.DEFINE_integer('port', 5000, 'Port to run the HTTP server on.')


def run_workers():
    coordinator = workers.get_coordinator()
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

    logging.basicConfig(
        format='%(levelname)s %(filename)s:%(lineno)s] %(message)s')
    if FLAGS.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

    if FLAGS.local_queue_workers:
        run_workers()

    if FLAGS.ignore_auth:
        server.app.config['IGNORE_AUTH'] = True

    server.app.run(debug=FLAGS.reload_code, port=FLAGS.port)


if __name__ == '__main__':
    main(sys.argv)
