#!/usr/bin/env python
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the webhooks module."""

import logging
import mock
import requests
import sys
import tempfile
import unittest

# Local libraries
import gflags
FLAGS = gflags.FLAGS

from dpxdt import server
from dpxdt.server import db
from dpxdt.server import models
from dpxdt.server import webhooks

WEBHOOK_TEST_URL = 'http://foobar.com/endpoint'

# This method will be used by the mock to replace requests.post
def mocked_requests_post(*args, **kwargs):
    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    if args[0] == WEBHOOK_TEST_URL:
        return MockResponse(200)
    else:
        return MockResponse(404)

def setUpModule():
    """Sets up the environment for testing."""
    db_path = tempfile.mktemp(suffix='.db')
    db.drop_all()
    db.create_all()


# Will be set by one-time setUp
ctx = None

class WebhooksTest(unittest.TestCase):
    """Tests for the webhooks module."""

    def setUp(self):
        global ctx
        ctx = server.app.test_request_context()
        ctx.push()
        self.build = models.Build(name='My build')
        db.session.add(self.build)
        db.session.commit()

        self.release = models.Release(name='My release',
                                      number=1,
                                      status=models.Release.PROCESSING,
                                      build_id=self.build.id)
        db.session.add(self.release)
        db.session.commit()

    def tearDown(self):
        ctx.pop()

    def addRunToRelease(self):
        run = models.Run(name='My run',
                         release_id=self.release.id,
                         status=models.Run.NEEDS_DIFF)
        db.session.add(run)
        db.session.commit()

    def testReadyForReviewWithNoRuns(self):
        response = webhooks.send_ready_for_review(self.build.id,
            self.release.name, self.release.number)
        assert response is None

    def testReadyForReviewWithRunsButNoWebhookUrlSet(self):
        self.addRunToRelease()
        response = webhooks.send_ready_for_review(self.build.id,
            self.release.name, self.release.number)
        assert response is None

    @mock.patch('dpxdt.server.webhooks.requests.post', side_effect=mocked_requests_post)
    def testReadyForReviewWithRunsAndWebhookUrl(self, mocked_requests_post):
        logging.info('testReadyForReviewWithRuns %s', self.build.webhook_url)
        self.build.webhook_url = WEBHOOK_TEST_URL
        db.session.add(self.build)
        db.session.commit()

        self.addRunToRelease()

        response = webhooks.send_ready_for_review(self.build.id,
            self.release.name, self.release.number)
        assert response.status_code == 200


def main(argv):
    try:
        argv = FLAGS(argv)
    except gflags.FlagsError, e:
        print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)

    logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(argv=argv)


if __name__ == '__main__':
    main(sys.argv)
