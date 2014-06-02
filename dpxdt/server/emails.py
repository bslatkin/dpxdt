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

"""Implements email sending for the API server and frontend."""

import logging

# Local libraries
from flask import render_template, request
from flask.ext.mail import Message
from flask.ext.login import current_user

# Local modules
from . import app
from . import mail
from dpxdt.server import models
from dpxdt.server import operations
from dpxdt.server import utils


def render_or_send(func, message):
    """Renders an email message for debugging or actually sends it."""
    if request.endpoint != func.func_name:
        mail.send(message)

    if (current_user.is_authenticated() and current_user.superuser):
        return render_template('debug_email.html', message=message)


@utils.ignore_exceptions
@app.route('/email/ready_for_review/<int:build_id>/'
           '<string:release_name>/<int:release_number>')
def send_ready_for_review(build_id, release_name, release_number):
    """Sends an email indicating that the release is ready for review."""
    build = models.Build.query.get(build_id)

    if not build.send_email:
        logging.debug(
            'Not sending ready for review email because build does not have '
            'email enabled. build_id=%r', build.id)
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

    title = '%s: %s - Ready for review' % (build.name, release.name)

    email_body = render_template(
        'email_ready_for_review.html',
        build=build,
        release=release,
        run_list=run_list,
        stats_dict=stats_dict)

    recipients = []
    if build.email_alias:
        recipients.append(build.email_alias)
    else:
        for user in build.owners:
            recipients.append(user.email_address)

    if not recipients:
        logging.debug(
            'Not sending ready for review email because there are no '
            'recipients. build_id=%r, release_name=%r, release_number=%d',
            build.id, release.name, release.number)
        return

    message = Message(title, recipients=recipients)
    message.html = email_body

    logging.info('Sending ready for review email for build_id=%r, '
                 'release_name=%r, release_number=%d to %r',
                 build.id, release.name, release.number, recipients)

    return render_or_send(send_ready_for_review, message)
