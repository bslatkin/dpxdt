#!/usr/bin/env python

"""Workers for driving screen captures, perceptual diffs, and related work."""

import Queue
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
  """Base work item that can be handled by a worker thread."""

  def __init__(self):
    self.error = None

  def __repr__(self):
    return '%s(%s)' % (self.__class__.__name__, repr(self.__dict__))


class WorkerThread(threading.Thread):
  """Base worker thread that handles items one at a time."""

  def __init__(self, input_queue, output_queue):
    """Initializer.

    Args:
      input_queue: Queue this worker consumes work from.
      output_queue: Queue where this worker puts new work items, if any.
    """
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
    """Handles a single item.

    Args:
      item: WorkItem to process.

    Returns:
      A WorkItem that should go on the output queue. If None, then the provided
      work item is considered finished and no additional work is needed.
    """
    raise NotImplemented


class ProcessItem(WorkItem):
  """Work item that is handled by running a subprocess."""

  def __init__(self, log_path, timeout_seconds=30):
    """Initializer.

    Args:
      log_path: Path to where output from this subprocess should be written.
      timeout_seconds: How long before the process should be force killed.
    """
    WorkItem.__init__(self)
    self.log_path = log_path
    self.timeout_seconds = timeout_seconds


class ProcessThread(WorkerThread):
  """Worker thread that runs subprocesses."""

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
  """Work item for capturing a website screenshot using PhantomJs."""

  def __init__(self, log_path, config_path, output_path):
    """Initializer.

    Args:
      log_path: Where to write the verbose logging output.
      config_path: Path to the screenshot config file to pass to PhantomJs.
      output_path: Where the output screenshot should be written.
    """
    ProcessItem.__init__(self, log_path)
    self.config_path = config_path
    self.output_path = output_path


class CaptureThread(ProcessThread):
  """Worker thread that runs PhantomJs."""

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
  """Work item for doing perceptual diffs using pdiff."""

  def __init__(self, log_path, ref_path, run_path, output_path):
    """Initializer.

    Args:
      log_path: Where to write the verbose logging output.
      ref_path: Path to reference screenshot to diff.
      run_path: Path to the most recent run screenshot to diff.
      output_path: Where the diff image should be written, if any.
    """
    ProcessItem.__init__(self, log_path)
    self.ref_path = ref_path
    self.run_path = run_path
    self.output_path = output_path


class DiffThread(ProcessThread):
  """Worker thread that runs pdiff."""

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
  """Work item for coordinating other work items.

  To use: Sub-class and override run(). Yield WorkItems you want processed
  as part of this workflow. Exceptions in child workflows will be reinjected
  into the run() generator at the yield point. Results will be available on
  the WorkItems returned by yield statements.
  """

  def __init__(self):
    WorkItem.__init__(self)

  def run(self):
    yield 'Yo dawg'


class WorkflowThread(WorkerThread):
  """Worker thread for running workflows."""

  def __init__(self, input_queue, output_queue):
    """Initializer.

    Args:
      input_queue: Queue this worker consumes work from. These should be
        WorkflowItems to process, or any WorkItems registered with this
        class using the register() method.
      output_queue: Queue where this worker puts finished work items, if any.
    """
    WorkerThread.__init__(self, input_queue, output_queue)
    self.pending = {}
    self.work_map = {}
    self.register(WorkflowItem, input_queue)

  def register(self, work_type, queue):
    """Registers where work for a specific type can be executed.

    Args:
      work_type: Sub-class of WorkItem to register.
      queue: Queue instance where WorkItems of the work_type should be
        enqueued when they are yielded by WorkflowItems being run by
        this worker.
    """
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
