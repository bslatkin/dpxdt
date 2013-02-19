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

"""Background worker that uploads new release candidates."""

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
FLAGS = gflags.FLAGS

# Local modules
import capture_worker
import pdiff_worker
import workers


gflags.DEFINE_string(
    'release_server_hostport', None,
    'Where the release server is located.')


class CreateReleaseWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, build_id, name):
        # create the release name with an API call
        # return it as the result


class ReportRunWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, build_id, name, number, screenshot_path, screenshot_log):
        # upload the screenshot
        # upload the log
        # save the result as a run


class ReportPdiffWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, reference_path, run_path, run_id):
        # Make a temp directory
        # upload the diff image
        # upload the diff log
        # report the fact that it's done
        # Delete the temp directory
