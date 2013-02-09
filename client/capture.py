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
gflags.DEFINE_string(
    'phantomjs_binary', None, 'Path to the phantomjs binary')

gflags.DEFINE_string(
    'phantomjs_script', None,
    'Path to the script that drives the phantomjs process')

gflags.DEFINE_integer(
    'polltime', 1,
    'How long to sleep between polling for work or subprocesses')


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


class ProcessThread(threading.Thread):
  """TODO"""

  def __init__(self, input_queue, output_queue, error_queue):
    threading.Thread.__init__(self)
    self.daemon = True
    self.input_queue = input_queue
    self.output_queue = output_queue
    self.error_queue = error_queue
    self.interrupted = False

  def run(self):
    while not self.interrupted:
      try:
        item = self.input_queue.get(True, FLAGS.polltime)
      except Queue.Empty:
        continue

      try:
        self.handle_item(item)
      except Exception, e:
        item.error = 'Exception. %s: %s' % (e.__class__.__name__, str(e))
        logging.exception('%s error item=%r %s',
                          self.worker_name, item, item.error)
        self.error_queue.put(item)
      else:
        self.output_queue.put(item)
      finally:
        self.input_queue.task_done()

  def get_args(self, item):
    raise NotImplemented

  @property
  def worker_name(self):
    return '%s:%s' % (self.__class__.__name__, self.ident)

  def handle_item(self, item):
    start_time = time.time()
    with open(item.log_path, 'w') as output_file:
      args = self.get_args(item)
      logging.info('%s start item=%r: %r', self.worker_name, item, args)
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
            raise TimeoutError('Sent SIGKILL to item=%r, pid=%s' % (
                               item, process.pid))

          time.sleep(FLAGS.polltime)
          continue

        if process.returncode != 0:
          raise BadReturnCodeError(process.returncode)

        logging.info('%s finished item=%r', self.worker_name, item)
        break


class CaptureThread(ProcessThread):
  """TODO"""

  def get_args(self, item):
    return [
        FLAGS.phantomjs_binary,
        '--disk-cache=false',
        '--debug=true',
        FLAGS.phantomjs_script,
        item.config_path,
    ]


def main(argv):
  try:
    argv = FLAGS(argv)
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  logging.getLogger().setLevel(logging.DEBUG)

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
