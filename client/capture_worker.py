#!/usr/bin/env python

"""Background worker that screenshots URLs, possibly from a queue."""

import Queue
import json
import logging
import subprocess
import sys
import threading
import time
import urllib2

# Local Libraries
import gflags

# Local modules
import workers


FLAGS = gflags.FLAGS

gflags.DEFINE_string(
    'phantomjs_binary', None, 'Path to the phantomjs binary')

gflags.DEFINE_string(
    'phantomjs_script', None,
    'Path to the script that drives the phantomjs process')


class CaptureItem(workers.ProcessItem):
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


class CaptureThread(workers.ProcessThread):
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


def register(coordinator=None):
  """Registers this module as a worker with the global coordinator."""
  if not coordinator:
    coordinator = workers.GetCoordinator()

  capture_queue = Queue.Queue()
  coordinator.register(CaptureItem, capture_queue)
  coordinator.worker_threads.append(
      CaptureThread(capture_queue, coordinator.input_queue))
