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


# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
import capture_worker
import pdiff_worker
import workers


gflags.DEFINE_string(
    'release_server_prefix', None,
    'URL prefix of where the release server is located, such as '
    '"http://www.example.com/here/is/my/api".')


class CreateReleaseWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, build_id, release_name):
        call = yield workers.FetchItem(
            FLAGS.release_server_prefix + '/create_release',
            post={
                'build_id': build_id,
                'release_name': release_name,
            })
        # TODO: Handle errors

        raise workers.Return(
            (build_id, release_name, call.json['release_number']))


class ReportRunWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, build_id, release_name, release_number,
            screenshot_path, screenshot_log):
        # upload the screenshot
        # upload the log
        # save the result as a run


class ReportPdiffWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, diff_path, diff_log, run_id):
        # upload the diff image
        # upload the diff log
        # report the fact that it's done


class RunsDoneWorkflow(workers.WorkflowItem):
    """TODO"""

    def run(self, build_id, release_name, release_number):
        # report the status to the server


