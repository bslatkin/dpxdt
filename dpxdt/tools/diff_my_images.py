#!/usr/bin/env python
# Copyright 2014 Brett Slatkin
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

"""Utility for uploading and diffing images that were generated locally.

Plugs screenshots generated in a tool like Selenium into Depicted. Uses the
last known good screenshots for tests with the same name as the baseline for
comparison. Depicted will generate diffs for you and manage the workflow.

Example usage:

./dpxdt/tools/diff_my_images.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    --upload_release_name="My release name" \
    --release_cut_url=http://example.com/path/to/my/release/tool/for/this/cut
    --tests_json_path=my_tests.json

Example input file "my_tests.json". One entry per test:

[
    {
        "name": "My homepage",
        "run_failed": false,
        "image_path": "/tmp/path/to/my/new_screenshot.png",
        "log_path": "/tmp/path/to/my/new_output_log.txt",
        "url": "http://example.com/new/build/url/here"
    },
    ...
]

Use the "run_failed" parameter when your screenshotting tool failed for
some reason and you want to upload your log but still mark the test as
having failed. This makes it easy to debug all of your Depicted tests in
one place for a single release.
"""

import datetime
import json
import logging
import sys

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import fetch_worker
from dpxdt.client import release_worker
from dpxdt.client import workers
import flags


class Test(object):
    """Represents the JSON of a single test."""

    def __init__(self, name=None, run_failed=False, image_path=None,
                 log_path=None, url=None):
        self.name = name
        self.run_failed = run_failed
        self.image_path = image_path
        self.log_path = log_path
        self.url = url


def load_tests(data):
    """Loads JSON data and returns a list of Test objects it contains."""
    test_list = json.loads(data)
    results = []
    for test_json in test_list:
        results.append(Test(**test_json))
    return results


class RunTest(workers.WorkflowItem):
    """Workflow to run a single test.

    Searches for the last good run for the same test name to use as a
    baseline for comparison. If no last good run is found, the supplied
    images will be treated as a new basline.

    Args:
        build_id: ID of the build being tested.
        release_name: Name of the release being tested.
        release_number: Number of the release being tested.
        test: Test object to handle.
        heartbeat: Function to call with progress status.
    """

    def run(self, build_id, release_name, release_number, test, heartbeat=None):
        ref_image, ref_log, ref_url = None, None, None
        try:
            last_good = yield release_worker.FindRunWorkflow(
                build_id, test.name)
        except release_worker.FindRunError, e:
            yield heartbeat('Could not find last good run for %s' % test.name)
        else:
            ref_image = last_good['image'] or None
            ref_log = last_good['log'] or None
            ref_url = last_good['url'] or None

        yield heartbeat('Uploading data for %s' % test.name)
        yield release_worker.ReportRunWorkflow(
            build_id,
            release_name,
            release_number,
            test.name,
            image_path=test.image_path,
            log_path=test.log_path,
            url=test.url,
            ref_image=ref_image,
            ref_log=ref_log,
            ref_url=ref_url,
            run_failed=test.run_failed)


class DiffMyImages(workers.WorkflowItem):
    """Workflow for diffing set of images generated outside of Depicted.

    Args:
        release_url: URL of the newest and best version of the page.
        tests: List of Test objects to test.
        upload_build_id: Optional. Build ID of the site being compared. When
            supplied a new release will be cut for this build comparing it
            to the last good release.
        upload_release_name: Optional. Release name to use for the build. When
            not supplied, a new release based on the current time will be
            created.
        heartbeat: Function to call with progress status.
    """

    def run(self,
            release_url,
            tests,
            upload_build_id,
            upload_release_name,
            heartbeat=None):
        if not upload_release_name:
            upload_release_name = str(datetime.datetime.utcnow())

        yield heartbeat('Creating release %s' % upload_release_name)
        release_number = yield release_worker.CreateReleaseWorkflow(
            upload_build_id, upload_release_name, release_url)

        pending_uploads = []
        for test in tests:
            item = RunTest(upload_build_id, upload_release_name,
                           release_number, test, heartbeat=heartbeat)
            pending_uploads.append(item)

        yield heartbeat('Uploading %d runs' % len(pending_uploads))
        yield pending_uploads

        yield heartbeat('Marking runs as complete')
        release_url = yield release_worker.RunsDoneWorkflow(
            upload_build_id, upload_release_name, release_number)

        yield heartbeat('Results viewable at: %s' % release_url)


def real_main(release_url=None,
              tests_json_path=None,
              upload_build_id=None,
              upload_release_name=None):
    """Runs diff_my_images."""
    coordinator = workers.get_coordinator()
    fetch_worker.register(coordinator)
    coordinator.start()

    data = open(FLAGS.tests_json_path).read()
    tests = load_tests(data)

    item = DiffMyImages(
        release_url,
        tests,
        upload_build_id,
        upload_release_name,
        heartbeat=workers.PrintWorkflow)
    item.root = True

    coordinator.input_queue.put(item)
    coordinator.wait_one()
    coordinator.stop()
    coordinator.join()


def main(argv):
    try:
        argv = FLAGS(argv)
    except gflags.FlagsError, e:
        print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)

    assert FLAGS.release_cut_url
    assert FLAGS.release_server_prefix
    assert FLAGS.tests_json_path
    assert FLAGS.upload_build_id

    if FLAGS.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    real_main(
        release_url=FLAGS.release_cut_url,
        tests_json_path=FLAGS.tests_json_path,
        upload_build_id=FLAGS.upload_build_id,
        upload_release_name=FLAGS.upload_release_name)


if __name__ == '__main__':
    main(sys.argv)
