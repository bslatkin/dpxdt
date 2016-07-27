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

import logging
import socket
import tempfile
import threading

# Local libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt import server
from dpxdt.server import db


def get_free_port():
    """Returns a free port number to listen on for testing."""
    sock = socket.socket()
    sock.bind(('', 0))
    return sock.getsockname()[1]


def start_server():
    """Starts the dpxdt server and returns its main thread."""
    server_port = get_free_port()

    FLAGS.fetch_frequency = 100
    FLAGS.fetch_threads = 1
    FLAGS.capture_timeout = 60
    FLAGS.polltime = 1
    FLAGS.queue_idle_poll_seconds = 1
    FLAGS.queue_busy_poll_seconds = 1
    FLAGS.queue_server_prefix = (
        'http://localhost:%d/api/work_queue' % server_port)
    FLAGS.release_server_prefix = 'http://localhost:%d/api' % server_port

    db_path = tempfile.mktemp(suffix='.db')
    logging.info('sqlite path used in tests: %s', db_path)
    server.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
    db.drop_all()
    db.create_all()

    server.app.config['CSRF_ENABLED'] = False
    server.app.config['IGNORE_AUTH'] = True
    server.app.config['TESTING'] = True
    run = lambda: server.app.run(debug=False, host='0.0.0.0', port=server_port)

    server_thread = threading.Thread(target=run)
    server_thread.setDaemon(True)
    server_thread.start()

    return server_thread


def debug_log_everything():
    logging.getLogger().setLevel(logging.DEBUG)
    for name in logging.Logger.manager.loggerDict.keys():
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
