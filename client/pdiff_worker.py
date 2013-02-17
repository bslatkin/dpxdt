#!/usr/bin/env python

"""Background worker that does perceptual diffs, possibly from a queue."""

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
    'pdiff_binary', None, 'Path to the perceptualdiff binary')



class PdiffItem(workers.ProcessItem):
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


class PdiffThread(workers.ProcessThread):
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


def register(coordinator=None):
  """Registers this module as a worker with the global coordinator."""
  if not coordinator:
    coordinator = workers.GetCoordinator()

  pdiff_queue = Queue.Queue()
  coordinator.register(PdiffItem, pdiff_queue)
  coordinator.worker_threads.append(
      PdiffThread(pdiff_queue, coordinator.input_queue))
