#!/usr/bin/env python
# Copyright 2015 Brett Slatkin
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

"""Implements sending webhooks for the API server."""

import logging
import requests

# Local libraries
import flask
from flask import url_for

from . import app
from dpxdt.server import models
from dpxdt.server import operations

NUM_RETRIES = 3

def _send_webhook(url, payload):
    attempt = 1
    while attempt < NUM_RETRIES + 1:
        try:
            response = requests.post(url, payload)
        except requests.exceptions.RequestException as e:
            logging.exception('Failed to send webhook to %s on attempt: %s', url, attempt)
            attempt += 1
        else:
            logging.info('Webhook sent to %s on attempt %s, got status_code=%d',
                         url, attempt, response.status_code)
            return response


def send_ready_for_review(build_id, release_name, release_number):
    build = models.Build.query.get(build_id)

    if not build.webhook_url:
        logging.debug(
            'Not sending ready for review webhook because build does not have '
            'webhook_url. build_id=%r', build.id)
        return

    ops = operations.BuildOps(build_id)
    release, run_list, stats_dict, _ = ops.get_release(
        release_name, release_number)

    if not run_list:
        logging.debug(
            'Not sending ready for review email because there are '
            ' no runs. build_id=%r, release_name=%r, release_number=%d',
            build.id, release.name, release.number)
        return

    view_build_url = url_for('view_build', id=build.id, _external=True)
    title = '%s: %s - Ready for review at %r' % (build.name, release.name, view_build_url)
    logging.info('Sending ready_for_review webhook. build_id=%r, url=%s', build.id, build.webhook_url)

    # Arbitrarily chose Slack payload format.
    # See https://api.slack.com/incoming-webhooks
    payload = {
        'text': title,
        'icon_url': url_for('static', filename='img/logo_big.png', _external=True)
    }
    return _send_webhook(build.webhook_url, payload)

