#!/usr/bin/env python

import Queue
import json
import logging
import subprocess
import sys
import threading
import time


# Local Libraries
import gflags

FLAGS = gflags.FLAGS
gflags.DEFINE_string('phantomjs_binary', None, 'Path to the phantomjs binary')
gflags.DEFINE_string('phantomjs_script', None,
                     'Path to the script that drives the phantomjs process')


class Error(Exception):
  """Base class for exceptions in this module."""


class TimeoutError(Exception):
  """Subprocess has taken too long to complete and was terminated."""


class BadReturnCodeError(Error):
  """Subprocess exited with a bad return code."""



class WorkItem(object):
  """TODO"""

  def __init__(self, config_path):
    """TODO
    file error if config not found
    key error if log path not found
    """
    self.config_path = config_path
    with open(config_path) as f:
      config = json.loads(f.read())
    self.log_path = config['logPath']
    self.timeout = config.get('timeout', 30)
    self.error = None

  def __repr__(self):
    return 'WorkItem(%s)' % repr(self.__dict__)


class CaptureThread(threading.Thread):
  """TODO"""

  def __init__(self, input_queue, output_queue, error_queue):
    threading.Thread.__init__(self)
    self.daemon = True
    self.input_queue = input_queue
    self.output_queue = output_queue
    self.error_queue = error_queue
    self.interrupted = False
    self.polltime = 1

  def run(self):
    while not self.interrupted:
      try:
        item = self.input_queue.get(True, self.polltime)
      except Queue.Empty:
        continue

      try:
        self.handle_item(item)
      except Exception, e:
        item.error = 'Exception. %s: %s' % (e.__class__.__name__, str(e))
        logging.exception('CaptureThread item=%r %s', item, item.error)
        self.error_queue.put(item)
      else:
        self.output_queue.put(item)
      finally:
        self.input_queue.task_done()

  def handle_item(self, item):
    start_time = time.time()
    with open(item.log_path, 'w') as output_file:
      args = [
          FLAGS.phantomjs_binary,
          '--disk-cache=false',
          '--debug=true',
          FLAGS.phantomjs_script,
          item.config_path,
      ]
      logging.info('Starting process: %r', args)
      process = subprocess.Popen(
        args,
        stderr=subprocess.STDOUT,
        stdout=output_file,
        close_fds=True)

      while True:
        process.poll()
        if process.returncode is None:
          now = time.time()
          if now - start_time > item.timeout or self.interrupted:
            process.kill()
            raise TimeoutError('Sent SIGKILL to pid=%s' % process.pid)

          time.sleep(self.polltime)
          continue

        if process.returncode != 0:
          raise BadReturnCodeError(process.returncode)

        break


def main(argv):
  try:
    argv = FLAGS(argv)
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  input_queue = Queue.Queue()
  output_queue = Queue.Queue()
  error_queue = Queue.Queue()

  t = CaptureThread(input_queue, output_queue, error_queue)
  t.start()

  item = WorkItem('config.js')
  input_queue.put(item)
  input_queue.join()


if __name__ == '__main__':
  main(sys.argv)
