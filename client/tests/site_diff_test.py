#!/usr/bin/env python

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
    self.test_dir = tempfile.mkdtemp('site_diff_test')
    # TODO: Move this flag to a parameter of the main function instead of
    # relying on a flag, so we can test the future hosted service thread.
    self.output_dir = join(self.test_dir, 'output')
    FLAGS.output_dir = self.output_dir

  def testFirstSnapshot(self):
    """Tests taking the very first snapshot."""
    @webserver
    def test(path):
      if path == '/':
        return 200, 'text/html', 'Hello world!'

    site_diff.real_main(['unused', 'http://%s:%d/' % test.server_address])
    test.shutdown()

    exists(join(self.output_dir, '__run.log'))
    exists(join(self.output_dir, '__run.png'))
    exists(join(self.output_dir, '__config.js'))
    exists(join(self.output_dir, 'url_paths.txt'))

    self.assertEquals(
        ['/'],
        open(join(self.output_dir, 'url_paths.txt')).readlines())

  def testNoDifferences(self):
    """Tests crawling the site end-to-end."""
    self.fail()

  def testOneDifference(self):
    """Tests when there is one found difference."""
    self.fail()

  def testNotFound(self):
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
