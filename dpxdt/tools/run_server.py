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

"""Runs the dpxdt server.

May provide the API server, queue workers, both together, or queue workers in
a local mode where they connect directly to the database instead of using
the API over HTTP.
"""

import logging
import os
import sys
import threading

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import capture_worker
from dpxdt.client import fetch_worker
from dpxdt.client import pdiff_worker
from dpxdt.client import timer_worker
from dpxdt.client import workers
from dpxdt import server


gflags.DEFINE_bool(
    'enable_api_server', False,
    'When true, run an API server on the local host.')

gflags.DEFINE_bool(
    'enable_queue_workers', False,
    'When true, run queue worker threads.')

gflags.DEFINE_bool(
    'local_workers', False,
    'When true, queue workers that are running locally will directly talk '
    'to the Database instead of accessing the API over HTTP.')

gflags.DEFINE_bool(
    'reload_code', False,
    'Reload code on every request. Should only be used in local development.')

gflags.DEFINE_bool(
    'ignore_auth', False,
    'Ignore any need for authentication for API and frontend accesses. You '
    'should only do this for local development!')

gflags.DEFINE_integer('port', 5000, 'Port to run the HTTP server on.')

gflags.DEFINE_string('host', '0.0.0.0', 'Host argument for the server.')


def run_workers():
    coordinator = workers.get_coordinator()
    capture_worker.register(coordinator)
    fetch_worker.register(coordinator)
    pdiff_worker.register(coordinator)
    timer_worker.register(coordinator)
    coordinator.start()
    return coordinator
    logging.info('Workers started')


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
    else:
        logging.getLogger().setLevel(logging.INFO)

    if FLAGS.verbose_queries:
        logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

    if FLAGS.enable_queue_workers:
        coordinator = run_workers()

        # If the babysitter thread dies, the whole process goes down.
        def worker_babysitter():
            try:
                coordinator.wait_one()
            finally:
                os._exit(1)

        babysitter_thread = threading.Thread(target=worker_babysitter)
        babysitter_thread.setDaemon(True)
        babysitter_thread.start()

    if FLAGS.ignore_auth:
        server.app.config['IGNORE_AUTH'] = True

    if FLAGS.enable_api_server:
        server.app.run(
            debug=FLAGS.reload_code,
            host=FLAGS.host,
            port=FLAGS.port)
    elif FLAGS.enable_queue_workers:
        coordinator.join()
    else:
        sys.exit('Must specify at least --enable_api_server or '
                 '--enable_queue_workers')


def run():
    # (intended to be run from package)
    main(sys.argv)


if __name__ == '__main__':
    run()
