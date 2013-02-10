#!/usr/bin/env python

"""TODO"""

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
gflags.DEFINE_string(
    'pdiff_binary', None, 'Path to the perceptualdiff binary')
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

  def __init__(self):
    self.error = None

  def __repr__(self):
    return '%s(%s)' % (self.__class__.__name__, repr(self.__dict__))


class WorkerThread(threading.Thread):
  """TODO"""

  def __init__(self, input_queue, output_queue):
    threading.Thread.__init__(self)
    self.daemon = True
    self.input_queue = input_queue
    self.output_queue = output_queue
    self.interrupted = False

  def run(self):
    while not self.interrupted:
      try:
        item = self.input_queue.get(True, FLAGS.polltime)
      except Queue.Empty:
        continue

      try:
        next_item = self.handle_item(item)
      except Exception, e:
        item.error = sys.exc_info()
        logging.error('%s error item=%r', self.worker_name, item)
        self.output_queue.put(item)
      else:
        logging.info('%s finished item=%r', self.worker_name, item)
        if next_item:
          self.output_queue.put(next_item)
      finally:
        self.input_queue.task_done()

  @property
  def worker_name(self):
    return '%s:%s' % (self.__class__.__name__, self.ident)

  def handle_item(self, item):
    raise NotImplemented


class ProcessItem(WorkItem):
  """TODO"""

  def __init__(self, log_path, timeout_seconds=30):
    WorkItem.__init__(self)
    self.log_path = log_path
    self.timeout_seconds = timeout_seconds


class ProcessThread(WorkerThread):
  """TODO"""

  def get_args(self, item):
    raise NotImplemented

  def handle_item(self, item):
    start_time = time.time()
    with open(item.log_path, 'w') as output_file:
      args = self.get_args(item)
      logging.info('%s item=%r Running subprocess: %r',
                   self.worker_name, item, args)
      process = subprocess.Popen(
        args,
        stderr=subprocess.STDOUT,
        stdout=output_file,
        close_fds=True)

      while True:
        process.poll()
        if process.returncode is None:
          now = time.time()
          if now - start_time > item.timeout_seconds or self.interrupted:
            process.kill()
            raise TimeoutError('Sent SIGKILL to item=%r, pid=%s' % (
                               item, process.pid))

          time.sleep(FLAGS.polltime)
          continue

        if process.returncode != 0:
          raise BadReturnCodeError(process.returncode)

        return item


class CaptureItem(ProcessItem):
  """TODO"""

  def __init__(self, log_path, config_path, output_path):
    """TODO
    file error if config not found
    key error if log path not found
    """
    ProcessItem.__init__(self, log_path)
    self.config_path = config_path
    self.output_path = output_path


class CaptureThread(ProcessThread):
  """TODO"""

  def get_args(self, item):
    return [
        FLAGS.phantomjs_binary,
        '--disk-cache=false',
        '--debug=true',
        FLAGS.phantomjs_script,
        item.config_path,
        item.output_path,
    ]


class DiffItem(ProcessItem):
  """TODO"""

  def __init__(self, log_path, ref_path, run_path, output_path):
    ProcessItem.__init__(self, log_path)
    self.ref_path = ref_path
    self.run_path = run_path
    self.output_path = output_path


class DiffThread(ProcessThread):
  """TODO"""

  def get_args(self, item):
    return [
        FLAGS.pdiff_binary,
        '-fov',
        '85',
        '-output',
        item.output_path,
        item.ref_path,
        item.run_path,
    ]


class WorkflowItem(WorkItem):
  """TODO"""

  def __init__(self):
    WorkItem.__init__(self)

  def run(self):
    yield None


class WorkflowThread(WorkerThread):
  """TODO

  Input queue is the output queue of all the others.
  Output queue is the
  """

  def __init__(self, input_queue, *args, **kwargs):
    WorkerThread.__init__(self, input_queue, *args, **kwargs)
    self.pending = {}
    self.work_map = {}
    self.register(WorkflowItem, input_queue)

  def register(self, work_type, queue):
    self.work_map[work_type] = queue

  def handle_item(self, item):
    if isinstance(item, WorkflowItem):
      workflow = item
      generator = item.run()
      item = None
    else:
      workflow, generator = self.pending.pop(item)

    try:
      if item and item.error:
        next_item = generator.throw(*item.error)
      else:
        next_item = generator.send(item)
    except StopIteration:
      return workflow

    target_queue = self.work_map[type(next_item)]
    self.pending[next_item] = (workflow, generator)
    target_queue.put(next_item)


class PdiffWorkflow(WorkflowItem):
  """TODO"""

  def run(self):
    ref = yield CaptureItem(
        '/tmp/test_ref.log',
        '/Users/bslatkin/projects/hostedpdiff/client/config.js',
        '/tmp/test_ref.png')
    run = yield CaptureItem(
        '/tmp/test_run.log',
        '/Users/bslatkin/projects/hostedpdiff/client/config.js',
        '/tmp/test_run.png')
    diff = yield DiffItem(
        '/tmp/test_diff.log', ref.output_path, run.output_path,
        '/tmp/test_diff.png')
    # If the diff has an error and the output file is present, then
    # we found a pixel diff. Otherwise if there is no error there is no diff.


def main(argv):
  try:
    argv = FLAGS(argv)
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  logging.getLogger().setLevel(logging.DEBUG)

  capture_queue = Queue.Queue()
  diff_queue = Queue.Queue()
  workflow_queue = Queue.Queue()
  complete_queue = Queue.Queue()

  coordinator = WorkflowThread(workflow_queue, complete_queue)
  coordinator.register(CaptureItem, capture_queue)
  coordinator.register(DiffItem, diff_queue)

  workers = [
    coordinator,
    CaptureThread(capture_queue, workflow_queue),
    DiffThread(diff_queue, workflow_queue),
  ]

  for worker in workers:
    worker.start()

  # Add in pdiff workers for new jobs
  # Retire them on error

  item = PdiffWorkflow()
  workflow_queue.put(item)
  result = complete_queue.get()
  if result.error:
    raise result.error[0], result.error[1], result.error[2]


if __name__ == '__main__':
  main(sys.argv)
