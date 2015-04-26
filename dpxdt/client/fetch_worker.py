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
import base64
import json
import logging
import shutil
import socket
import ssl
import time
import urllib
import urllib2

# Local Libraries
import gflags
FLAGS = gflags.FLAGS
import poster.encode
import poster.streaminghttp
poster.streaminghttp.register_openers()

# Local modules
from dpxdt.client import workers


LOGGER = workers.LOGGER


gflags.DEFINE_float(
    'fetch_frequency', 1.0,
    'Maximum number of fetches to make per second per thread.')

gflags.DEFINE_integer(
    'fetch_threads', 1, 'Number of fetch threads to run')

gflags.DEFINE_bool(
    'fetch_use_internal_redirects', False,
    'When doing URL fetches, always direct the request to the local server. '
    'This assumes that any URL fetches are actually API calls back to the '
    'server itself. This allows you to deploy an API server and worker '
    'process in a firewall configuration where sockets can come in but they '
    'can\'t go out.')


class FetchItem(workers.WorkItem):
    """Work item that is handled by fetching a URL."""

    def __init__(self,
                 url,
                 post=None,
                 timeout_seconds=30,
                 result_path=None,
                 username=None,
                 password=None):
        """Initializer.

        Args:
            url: URL to fetch.
            post: Optional. Dictionary of post parameters to include in the
                request, with keys and values coerced to strings. If any
                values are open file handles, the post data will be formatted
                as multipart/form-data.
            timeout_seconds: Optional. How long until the fetch should timeout.
            result_path: When supplied, the output of the fetch should be
                streamed to a file on disk with the given path. Use this
                to prevent many fetches from causing memory problems.
            username: Optional. Username to use for the request, for
                HTTP basic authentication.
            password: Optional. Password to use for the request, for
                HTTP basic authentication.
        """
        workers.WorkItem.__init__(self)
        self.url = url
        self.post = post
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.result_path = result_path
        # Response values
        self.status_code = None
        self.data = None
        self._data_json = None
        self.content_type = None

    def _get_dict_for_repr(self):
        result = self.__dict__.copy()
        if result.get('password'):
            result['password'] = 'ELIDED'
        return result

    @property
    def json(self):
        """Returns de-JSONed data or None if it's a different content type."""
        if self._data_json:
            return self._data_json

        if not self.data or self.content_type != 'application/json':
            return None

        self._data_json = json.loads(self.data)
        return self._data_json


def fetch_internal(item, request):
    """Fetches the given request by using the local Flask context."""
    # Break client dependence on Flask if internal fetches aren't being used.
    from flask import make_response
    from werkzeug.test import EnvironBuilder
    # Break circular dependencies.
    from dpxdt.server import app

    # Attempt to create a Flask environment from a urllib2.Request object.
    environ_base = {
        'REMOTE_ADDR': '127.0.0.1',
    }

    # The data object may be a generator from poster.multipart_encode, so we
    # need to convert that to raw bytes here. Unfortunately EnvironBuilder
    # only works with the whole request buffered in memory.
    data = request.get_data()
    if data and not isinstance(data, str):
        data = ''.join(list(data))

    builder = EnvironBuilder(
        path=request.get_selector(),
        base_url='%s://%s' % (request.get_type(), request.get_host()),
        method=request.get_method(),
        data=data,
        headers=request.header_items(),
        environ_base=environ_base)

    with app.request_context(builder.get_environ()):
        response = make_response(app.dispatch_request())
        LOGGER.info('"%s" %s via internal routing',
                    request.get_selector(), response.status_code)
        item.status_code = response.status_code
        item.content_type = response.mimetype
        if item.result_path:
            # TODO: Is there a better way to access the response stream?
            with open(item.result_path, 'wb') as result_file:
                for piece in response.iter_encoded():
                    result_file.write(piece)
        else:
            item.data = response.get_data()

    return item


def fetch_normal(item, request):
    """Fetches the given request over HTTP."""
    try:
        conn = urllib2.urlopen(request, timeout=item.timeout_seconds)
    except urllib2.HTTPError, e:
        conn = e
    except (urllib2.URLError, ssl.SSLError), e:
        # TODO: Make this status more clear
        item.status_code = 400
        return item

    try:
        item.status_code = conn.getcode()
        item.content_type = conn.info().gettype()
        if item.result_path:
            with open(item.result_path, 'wb') as result_file:
                shutil.copyfileobj(conn, result_file)
        else:
            item.data = conn.read()
    except socket.timeout, e:
        # TODO: Make this status more clear
        item.status_code = 400
        return item
    finally:
        conn.close()

    return item


class FetchThread(workers.WorkerThread):
    """Worker thread for fetching URLs."""

    def handle_item(self, item):
        start_time = time.time()

        if item.post is not None:
            adjusted_data = {}
            use_form_data = False

            for key, value in item.post.iteritems():
                if value is None:
                    continue
                if isinstance(value, file):
                    use_form_data = True
                adjusted_data[key] = value

            if use_form_data:
                datagen, headers = poster.encode.multipart_encode(
                    adjusted_data)
                request = urllib2.Request(item.url, datagen, headers)
            else:
                post_data = urllib.urlencode(adjusted_data)
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Content-Length': len(post_data),
                }
                request = urllib2.Request(item.url, post_data, headers)
        else:
            request = urllib2.Request(item.url)

        if item.username:
            credentials = base64.b64encode(
                '%s:%s' % (item.username, item.password))
            request.add_header('Authorization', 'Basic %s' % credentials)

        try:
            if FLAGS.fetch_use_internal_redirects:
                return fetch_internal(item, request)
            else:
                return fetch_normal(item, request)
        finally:
            end_time = time.time()
            wait_duration = (1.0 / FLAGS.fetch_frequency) - (
                end_time - start_time)
            if wait_duration > 0:
                LOGGER.debug('Rate limiting URL fetch for %f seconds',
                             wait_duration)
                time.sleep(wait_duration)


def register(coordinator):
    """Registers this module as a worker with the given coordinator."""
    fetch_queue = Queue.Queue()
    coordinator.register(FetchItem, fetch_queue)
    for i in xrange(FLAGS.fetch_threads):
        coordinator.worker_threads.append(
            FetchThread(fetch_queue, coordinator.input_queue))
