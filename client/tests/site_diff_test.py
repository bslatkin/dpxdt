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

"""Tests for the site_diff utility.

To run:

./tests/site_diff_test.py \
  --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
  --phantomjs_script=path/to/client/capture.js \
  --pdiff_binary=path/to/pdiff/perceptualdiff
"""

import BaseHTTPServer
import logging
import os
import sys
import tempfile
import threading
import unittest


# Local libraries
import gflags
import site_diff
import workers


FLAGS = gflags.FLAGS


# For convenience
exists = os.path.exists
join = os.path.join


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

    self.assertEquals('http://www.example.com/this/is/scheme-relative.html',
                      test('//www.example.com/this/is/scheme-relative.html'))

    self.assertEquals('http://www.example.com/okay-then',  # Scheme changed
                      test('https://www.example.com/okay-then#blah'))

    self.assertEquals('http://www.example.com/another-one',
                      test('http://www.example.com/another-one'))

    self.assertEquals('http://www.example.com/this-has/a',
                      test('/this-has/a?query=string'))

    self.assertEquals('http://www.example.com/this-also-has/a/',
                      test('/this-also-has/a/?query=string&but=more-complex'))

    self.assertEquals(
        'http://www.example.com/relative-with/some-(parenthesis%20here)',
        test('/relative-with/some-(parenthesis%20here)'))

    self.assertEquals(
        'http://www.example.com/relative-with/some-(parenthesis%20here)',
        test('//www.example.com/relative-with/some-(parenthesis%20here)'))

    self.assertEquals(
        'http://www.example.com/relative-with/some-(parenthesis%20here)',
        test('http://www.example.com/relative-with/some-(parenthesis%20here)'))


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
  return server


class SiteDiffTest(unittest.TestCase):
  """Tests for the SiteDiff workflow."""

  def setUp(self):
    """Sets up the test harness."""
    FLAGS.fetch_frequency = 100
    FLAGS.polltime = 0.01
    self.test_dir = tempfile.mkdtemp('site_diff_test')
    self.output_dir = join(self.test_dir, 'output')
    self.reference_dir = join(self.test_dir, 'reference')
    self.coordinator = workers.GetCoordinator()

  def output_readlines(self, path):
    """Reads the lines of an output file, stripping newlines."""
    return [
      x.strip() for x in open(join(self.output_dir, path)).xreadlines()]

  def testFirstSnapshot(self):
    """Tests taking the very first snapshot."""
    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', 'Hello world!'

    site_diff.real_main(
        'http://%s:%d/' % test.server_address, [], self.output_dir, None,
        coordinator=self.coordinator)
    test.shutdown()

    self.assertTrue(exists(join(self.output_dir, '__run.log')))
    self.assertTrue(exists(join(self.output_dir, '__run.png')))
    self.assertTrue(exists(join(self.output_dir, '__config.js')))
    self.assertTrue(exists(join(self.output_dir, 'url_paths.txt')))

    self.assertEquals(
        ['/'],
        self.output_readlines('url_paths.txt'))

  def testNoDifferences(self):
    """Tests crawling the site end-to-end."""
    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', 'Hello world!'

    site_diff.real_main(
        'http://%s:%d/' % test.server_address, [], self.reference_dir, None,
        coordinator=self.coordinator)

    self.coordinator = workers.GetCoordinator()
    site_diff.real_main(
        'http://%s:%d/' % test.server_address, [],
        self.output_dir, self.reference_dir,
        coordinator=self.coordinator)
    test.shutdown()

    self.assertTrue(exists(join(self.reference_dir, '__run.log')))
    self.assertTrue(exists(join(self.reference_dir, '__run.png')))
    self.assertTrue(exists(join(self.reference_dir, '__config.js')))
    self.assertTrue(exists(join(self.reference_dir, 'url_paths.txt')))

    self.assertTrue(exists(join(self.output_dir, '__run.log')))
    self.assertTrue(exists(join(self.output_dir, '__run.png')))
    self.assertTrue(exists(join(self.output_dir, '__ref.log')))
    self.assertTrue(exists(join(self.output_dir, '__ref.png')))
    self.assertFalse(exists(join(self.output_dir, '__diff.png')))  # No diff
    self.assertTrue(exists(join(self.output_dir, '__diff.log')))
    self.assertTrue(exists(join(self.output_dir, '__config.js')))
    self.assertTrue(exists(join(self.output_dir, 'url_paths.txt')))

  def testOneDifference(self):
    """Tests when there is one found difference."""
    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', 'Hello world!'

    site_diff.real_main(
        'http://%s:%d/' % test.server_address, [], self.reference_dir, None,
        coordinator=self.coordinator)
    test.shutdown()

    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', 'Hello world a little different!'

    self.coordinator = workers.GetCoordinator()
    site_diff.real_main(
        'http://%s:%d/' % test.server_address, [],
        self.output_dir, self.reference_dir,
        coordinator=self.coordinator)
    test.shutdown()

    self.assertTrue(exists(join(self.reference_dir, '__run.log')))
    self.assertTrue(exists(join(self.reference_dir, '__run.png')))
    self.assertTrue(exists(join(self.reference_dir, '__config.js')))
    self.assertTrue(exists(join(self.reference_dir, 'url_paths.txt')))

    self.assertTrue(exists(join(self.output_dir, '__run.log')))
    self.assertTrue(exists(join(self.output_dir, '__run.png')))
    self.assertTrue(exists(join(self.output_dir, '__ref.log')))
    self.assertTrue(exists(join(self.output_dir, '__ref.png')))
    self.assertTrue(exists(join(self.output_dir, '__diff.png')))  # Diff!!
    self.assertTrue(exists(join(self.output_dir, '__diff.log')))
    self.assertTrue(exists(join(self.output_dir, '__config.js')))
    self.assertTrue(exists(join(self.output_dir, 'url_paths.txt')))

  def testCrawler(self):
    """Tests that the crawler behaves well.

    Specifically:
      - Finds new links in HTML data
      - Avoids non-HTML pages
      - Respects ignore patterns specified on flags
    """
    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', (
            'Hello world! <a href="/stuff">x</a> <a href="/ignore">y</a>')
      elif path == '/stuff':
        return 200, 'text/html', 'Stuff page <a href="/avoid">x</a>'
      elif path == '/avoid':
        return 200, 'text/plain', 'Ignore me!'

    site_diff.real_main(
        'http://%s:%d/' % test.server_address, ['/ignore'],
        self.output_dir, None,
        coordinator=self.coordinator)
    test.shutdown()

    self.assertTrue(exists(join(self.output_dir, '__run.log')))
    self.assertTrue(exists(join(self.output_dir, '__run.png')))
    self.assertTrue(exists(join(self.output_dir, '__config.js')))
    self.assertTrue(exists(join(self.output_dir, 'url_paths.txt')))

    self.assertEquals(
        ['/', '/stuff'],
        self.output_readlines('url_paths.txt'))

  def testNotFound(self):
    """Tests when a URL in the crawl is not found."""
    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', (
            'Hello world! <a href="/missing">x</a>')
      elif path == '/missing':
        return 404, 'text/plain', 'Nope'

    site_diff.real_main(
        'http://%s:%d/' % test.server_address, ['/ignore'],
        self.output_dir, None,
        coordinator=self.coordinator)
    test.shutdown()

    self.assertTrue(exists(join(self.output_dir, '__run.log')))
    self.assertTrue(exists(join(self.output_dir, '__run.png')))
    self.assertTrue(exists(join(self.output_dir, '__config.js')))
    self.assertTrue(exists(join(self.output_dir, 'url_paths.txt')))

    self.assertEquals(
        ['/'],
        self.output_readlines('url_paths.txt'))

    self.fail()

  def testDiffNotLinkedUrlsFound(self):
    """Tests when a URL in the old set exists but is not linked."""
    self.fail()

  def testDiffNotFound(self):
    """Tests when a URL in the old set is a 404 in the new set."""
    self.fail()

  def testSuccessAfterRetry(self):
    """Tests that URLs that return errors will be retried."""
    self.fail()

  def testFailureAfterRetry(self):
    """Tests when repeated retries of a URL fail."""
    self.fail()


def main(argv):
  gflags.MarkFlagAsRequired('phantomjs_binary')
  gflags.MarkFlagAsRequired('phantomjs_script')
  gflags.MarkFlagAsRequired('pdiff_binary')

  try:
    argv = FLAGS(argv)
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main(argv=argv)


if __name__ == '__main__':
  main(sys.argv)
