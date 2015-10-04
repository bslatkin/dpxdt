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

"""Tests for the site_diff utility."""

import BaseHTTPServer
import logging
import os
import sys
import threading
import time
import unittest
import uuid

# Local libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt import server
from dpxdt.client import capture_worker
from dpxdt.client import workers
from dpxdt.server import db
from dpxdt.server import models
from dpxdt.tools import run_server
from dpxdt.tools import site_diff

# Test-only modules
import test_utils


# Will be set by one-time setUp
server_thread = None


def setUpModule():
    """Sets up the environment for testing."""
    global server_thread
    server_thread = test_utils.start_server()
    run_server.run_workers()


def create_build():
    """Creates a new build and returns its ID."""
    build = models.Build(name='My build')
    db.session.add(build)
    db.session.commit()
    return build.id


def wait_for_release(build_id, release_name, timeout_seconds=60):
    """Waits for a release to enter a terminal state."""
    start = time.time()
    while True:
        release = (models.Release.query
            .filter_by(build_id=build_id, name=release_name)
            .order_by(models.Release.number.desc())
            .first())
        db.session.refresh(release)
        if release.status == models.Release.REVIEWING:
            return release
        else:
            logging.info('Release status: %s', release.status)

        assert time.time() - start < timeout_seconds, (
            'Timing out waiting for release to enter terminal state')
        time.sleep(1)


def webserver(func):
    """Runs the given function as a webserver.

    Function should take one argument, the path of the request. Should
    return tuple (status, content_type, content) or Nothing if there is no
    response.
    """
    class HandlerClass(BaseHTTPServer.BaseHTTPRequestHandler):
        def do_GET(self):
            output = func(self.path)
            if output:
                code, content_type, result = output
            else:
                code, content_type, result = 404, 'text/plain', 'Not found!'

            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            if result:
                self.wfile.write(result)

    server = BaseHTTPServer.HTTPServer(('', 0), HandlerClass)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    server.server_prefix = 'http://localhost:%d' % server.server_address[1]
    logging.info('Test server started on %s', server.server_prefix)
    return server


class SiteDiffTest(unittest.TestCase):
    """Tests for the SiteDiff workflow."""

    def setUp(self):
        """Sets up the test harness."""
        self.coordinator = workers.get_coordinator()
        self.build_id = create_build()
        self.release_name = uuid.uuid4().hex
        self.client = server.app.test_client()

    def testEndToEnd(self):
        """Tests doing a site diff from end to end."""
        # Create the first release.
        @webserver
        def test1(path):
            if path == '/':
                return 200, 'text/html', '<h1>Hello world!</h1>'

        logging.info('Creating first release')
        site_diff.real_main(
            start_url=test1.server_prefix + '/',
            upload_build_id=self.build_id,
            upload_release_name=self.release_name)

        logging.info('Waiting for first release')
        release = wait_for_release(self.build_id, self.release_name)

        # Verify the first screenshot worked and its status can load.
        logging.info('Checking first screenshot')
        resp = self.client.get(
            '/release?id=%d&name=%s&number=%d' % (
                self.build_id, release.name, release.number),
            follow_redirects=True)
        self.assertEquals('200 OK', resp.status)
        self.assertIn('Nothing to test', resp.data)
        self.assertIn('Diff not required', resp.data)

        # Mark the release as good.
        logging.info('Marking first release as good')
        resp = self.client.post(
            '/release',
            data=dict(
                id=self.build_id,
                name=release.name,
                number=release.number,
                good=True),
            follow_redirects=True)
        self.assertEquals('200 OK', resp.status)

        # Create the second release.
        @webserver
        def test2(path):
            if path == '/':
                return 200, 'text/html', '<h1>Hello again!</h1>'

        logging.info('Creating second release')
        site_diff.real_main(
            start_url=test2.server_prefix + '/',
            upload_build_id=self.build_id,
            upload_release_name=self.release_name)

        logging.info('Waiting for second release')
        release = wait_for_release(self.build_id, self.release_name)

        # Verify a diff was computed and found.
        logging.info('Checking second screenshot has a diff')
        resp = self.client.get(
            '/release?id=%d&name=%s&number=%d' % (
                self.build_id, release.name, release.number),
            follow_redirects=True)
        self.assertEquals('200 OK', resp.status)
        self.assertIn('1 tested', resp.data)
        self.assertIn('1 failure', resp.data)
        self.assertIn('Diff found', resp.data)

        # Create the third release.
        logging.info('Creating third release')
        site_diff.real_main(
            start_url=test1.server_prefix + '/',
            upload_build_id=self.build_id,
            upload_release_name=self.release_name)

        logging.info('Waiting for third release')
        release = wait_for_release(self.build_id, self.release_name)
        test1.shutdown()
        test2.shutdown()

        # No diff found.
        logging.info('Checking third screenshot has no diff')
        resp = self.client.get(
            '/release?id=%d&name=%s&number=%d' % (
                self.build_id, release.name, release.number),
            follow_redirects=True)
        self.assertEquals('200 OK', resp.status)
        self.assertIn('1 tested', resp.data)
        self.assertIn('All passing', resp.data)

    def testCrawler(self):
        """Tests that the crawler behaves well.

        Specifically:
            - Finds new links in HTML data
            - Avoids non-HTML pages
            - Respects ignore patterns specified on flags
            - Properly handles 404s
        """
        @webserver
        def test(path):
            if path == '/':
                return 200, 'text/html', (
                    'Hello world! <a href="/stuff">x</a> '
                    '<a href="/ignore">y</a> and also '
                    '<a href="/missing">z</a>')
            elif path == '/stuff':
                return 200, 'text/html', 'Stuff page <a href="/avoid">x</a>'
            elif path == '/missing':
                return 404, 'text/plain', 'Nope'
            elif path == '/avoid':
                return 200, 'text/plain', 'Ignore me!'

        site_diff.real_main(
            start_url=test.server_prefix + '/',
            upload_build_id=self.build_id,
            upload_release_name=self.release_name,
            ignore_prefixes=['/ignore'])

        release = wait_for_release(self.build_id, self.release_name)
        run_list = models.Run.query.all()
        found = set(run.name for run in run_list)

        expected = set(['/', '/stuff'])
        self.assertEquals(expected, found)

        test.shutdown()


class HtmlRewritingTest(unittest.TestCase):
    """Tests the HTML rewriting functions."""

    def testAll(self):
        """Tests all the variations."""
        base_url = 'http://www.example.com/my-url/here'
        def test(test_url):
            data = '<a href="%s">my link here</a>' % test_url
            result = site_diff.extract_urls(base_url, data)
            if not result:
                return None
            return list(result)[0]

        self.assertEquals('http://www.example.com/my-url/dummy_page2.html',
                          test('dummy_page2.html'))

        self.assertEquals('http://www.example.com/',
                          test('/'))

        self.assertEquals('http://www.example.com/mypath-here',
                          test('/mypath-here'))

        self.assertEquals(None, test('#fragment-only'))

        self.assertEquals('http://www.example.com/my/path/over/here.html',
                          test('/my/path/01/13/../../over/here.html'))

        self.assertEquals('http://www.example.com/my/path/01/over/here.html',
                          test('/my/path/01/13/./../over/here.html'))

        self.assertEquals('http://www.example.com/my-url/same-directory.html',
                          test('same-directory.html'))

        self.assertEquals('http://www.example.com/relative-but-no/child',
                          test('../../relative-but-no/child'))

        self.assertEquals('http://www.example.com/too/many/relative/paths',
                          test('../../../../too/many/relative/paths'))

        self.assertEquals(
            'http://www.example.com/this/is/scheme-relative.html',
            test('//www.example.com/this/is/scheme-relative.html'))

        self.assertEquals(
            'http://www.example.com/okay-then',    # Scheme changed
            test('https://www.example.com/okay-then#blah'))

        self.assertEquals('http://www.example.com/another-one',
                          test('http://www.example.com/another-one'))

        self.assertEquals('http://www.example.com/this-has/a',
                          test('/this-has/a?query=string'))

        self.assertEquals(
            'http://www.example.com/this-also-has/a/',
            test('/this-also-has/a/?query=string&but=more-complex'))

        self.assertEquals(
            'http://www.example.com/relative-with/some-(parenthesis%20here)',
            test('/relative-with/some-(parenthesis%20here)'))

        self.assertEquals(
            'http://www.example.com/relative-with/some-(parenthesis%20here)',
            test('//www.example.com/relative-with/some-(parenthesis%20here)'))

        self.assertEquals(
            'http://www.example.com/relative-with/some-(parenthesis%20here)',
            test('http://www.example.com/relative-with/some-'
                 '(parenthesis%20here)'))

        self.assertIsNone(test('mailto:bob@example.com'))

        # Known bad results
        self.assertEquals(
            'http://www.example.com/my-url/ftp://bob@www.example.com/',
            test('ftp://bob@www.example.com/'))

        self.assertEquals(
            'http://www.example.com/my-url/javascript:runme()',
            test('javascript:runme()'))

        self.assertEquals(
            'http://www.example.com/my-url/tel:1-555-555-5555',
            test('tel:1-555-555-5555'))

        self.assertEquals('http://www.example.com/test.js',
                          test('/test.js'))

        # Escaped sources (e.g. inside inline JavaScript) are scraped,
        # even though they shouldn't be.
        scriptTag = ('<script type=\"text\/javascript\"'
            ' src=\"\/\/platform.twitter.com\/widgets.js\"><\/script>')
        self.assertEquals(
            set([
                'http://www.example.com/my-url/'
                '\\/\\/platform.twitter.com\\/widgets.js'
            ]),
            site_diff.extract_urls(base_url, scriptTag))

        spacesInTag = "<a href = 'spaced.html'>"
        self.assertEquals(
            set(['http://www.example.com/my-url/spaced.html']),
            site_diff.extract_urls(base_url, spacesInTag))

        # JavaScript variable assignment isn't handled correctly.
        jsText = "var src = true;"
        self.assertEquals(
            set([
                'http://www.example.com/my-url/true'
            ]),
            site_diff.extract_urls(base_url, jsText))


def main(argv):
    gflags.MarkFlagAsRequired('phantomjs_binary')
    gflags.MarkFlagAsRequired('phantomjs_script')

    try:
        argv = FLAGS(argv)
    except gflags.FlagsError, e:
        print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)

    test_utils.debug_log_everything()
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
