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

"""Utility for diffing a set of URL pairs defined in a config file.

Example usage:

./dpxdt/tools/diff_my_urls.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    --upload_release_name="My release name" \
    --release_cut_url=http://example.com/path/to/my/release/tool/for/this/cut
    --tests_json_path=my_url_tests.json

Example input file "my_url_tests.json". One entry per test:

[
    {
        "name": "My homepage",
        "run_url": "http://localhost:5000/static/dummy/dummy_page1.html",
        "run_config": {
            "viewportSize": {
                "width": 1024,
                "height": 768
            },
            "injectCss": "#foobar { background-color: lime",
            "injectJs": "document.getElementById('foobar').innerText = 'bar';",
        },
        "ref_url": "http://localhost:5000/static/dummy/dummy_page1.html",
        "ref_config": {
            "viewportSize": {
                "width": 1024,
                "height": 768
            },
            "injectCss": "#foobar { background-color: goldenrod; }",
            "injectJs": "document.getElementById('foobar').innerText = 'foo';",
        }
    },
    ...
]

See README.md for documentation of config parameters.
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

    def __init__(self, name=None, run_url=None, run_config=None,
                 ref_url=None, ref_config=None):
        self.name = name
        self.run_url = run_url
        self.run_config_data = json.dumps(run_config)
        self.ref_url = ref_url
        self.ref_config_data = json.dumps(ref_config)


def load_tests(data):
    """Loads JSON data and returns a list of Test objects it contains."""
    test_list = json.loads(data)
    results = []
    for test_json in test_list:
        results.append(Test(**test_json))
    return results


class DiffMyUrls(workers.WorkflowItem):
    """Workflow for diffing a set of URL pairs defined in a config file.

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
            item = release_worker.RequestRunWorkflow(
                upload_build_id, upload_release_name, release_number,
                test.name, url=test.run_url, config_data=test.run_config_data,
                ref_url=test.ref_url, ref_config_data=test.ref_config_data)
            pending_uploads.append(item)

        yield heartbeat('Requesting %d runs' % len(pending_uploads))
        yield pending_uploads

        yield heartbeat('Marking runs as complete')
        release_url = yield release_worker.RunsDoneWorkflow(
            upload_build_id, upload_release_name, release_number)

        yield heartbeat('Results viewable at: %s' % release_url)


def real_main(release_url=None,
              tests_json_path=None,
              upload_build_id=None,
              upload_release_name=None):
    """Runs diff_my_urls."""
    coordinator = workers.get_coordinator()
    fetch_worker.register(coordinator)
    coordinator.start()

    data = open(FLAGS.tests_json_path).read()
    tests = load_tests(data)

    item = DiffMyUrls(
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
