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

"""Common utility functions."""

import base64
import datetime
import hashlib
import functools
import logging
import os
import traceback
import uuid

# Local libraries
import flask
from flask import abort, g, jsonify
from sqlalchemy.exc import OperationalError

# Local modules
from . import app
from . import db


def retryable_transaction(attempts=3, exceptions=(OperationalError,)):
    """Decorator retries a function when expected exceptions are raised."""
    assert len(exceptions) > 0
    assert attempts > 0

    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            for i in xrange(attempts):
                try:
                    return f(*args, **kwargs)
                except exceptions, e:
                    if i == (attempts - 1):
                        raise
                    logging.warning(
                        'Retryable error in transaction on attempt %d. %s: %s',
                        i + 1, e.__class__.__name__, e)
                    db.session.rollback()

        return wrapped

    return wrapper


def jsonify_assert(asserted, message, status_code=400):
    """Asserts something is true, aborts the request if not."""
    if asserted:
        return
    try:
        raise AssertionError(message)
    except AssertionError, e:
        stack = traceback.extract_stack()
        stack.pop()
        logging.error('Assertion failed: %s\n%s',
                      str(e), ''.join(traceback.format_list(stack)))
        abort(jsonify_error(e, status_code=status_code))


def jsonify_error(message_or_exception, status_code=400):
    """Returns a JSON payload that indicates the request had an error."""
    if isinstance(message_or_exception, Exception):
        message = '%s: %s' % (
            message_or_exception.__class__.__name__, message_or_exception)
    else:
        message = message_or_exception

    logging.debug('Returning status=%d, error message: %s',
                  status_code, message)
    response = jsonify(error=message)
    response.status_code = status_code
    return response


def ignore_exceptions(f):
    """Decorator catches and ignores any exceptions raised by this function."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            logging.exception("Ignoring exception in %r", f)
    return wrapped


# Based on http://flask.pocoo.org/snippets/33/
@app.template_filter()
def timesince(when):
    """Returns string representing "time since" or "time until".

    Examples:
        3 days ago, 5 hours ago, 3 minutes from now, 5 hours from now, now.
    """
    if not when:
        return ''

    now = datetime.datetime.utcnow()
    if now > when:
        diff = now - when
        suffix = 'ago'
    else:
        diff = when - now
        suffix = 'from now'

    periods = (
        (diff.days / 365, 'year', 'years'),
        (diff.days / 30, 'month', 'months'),
        (diff.days / 7, 'week', 'weeks'),
        (diff.days, 'day', 'days'),
        (diff.seconds / 3600, 'hour', 'hours'),
        (diff.seconds / 60, 'minute', 'minutes'),
        (diff.seconds, 'second', 'seconds'),
    )

    for period, singular, plural in periods:
        if period:
            return '%d %s %s' % (
                period,
                singular if period == 1 else plural,
                suffix)

    return 'now'


def human_uuid():
    """Returns a good UUID for using as a human readable string."""
    return base64.b32encode(
        hashlib.sha1(uuid.uuid4().bytes).digest()).lower().strip('=')


def password_uuid():
    """Returns a good UUID for using as a password."""
    return base64.b64encode(
        hashlib.sha1(uuid.uuid4().bytes).digest()).strip('=')


def is_production():
    """Returns True if this is the production environment."""
    # TODO: Support other deployment situations.
    return (
        os.environ.get('SERVER_SOFTWARE', '').startswith('Google App Engine'))


def get_deployment_timestamp():
    """Returns a unique string represeting the current deployment.

    Used for busting caches.
    """
    # TODO: Support other deployment situations.
    if os.environ.get('SERVER_SOFTWARE', '').startswith('Google App Engine'):
        version_id = os.environ.get('CURRENT_VERSION_ID')
        major_version, timestamp = version_id.split('.', 1)
        return timestamp
    return 'test'


# From http://flask.pocoo.org/snippets/53/
def after_this_request(func):
    if not hasattr(g, 'call_after_request'):
        g.call_after_request = []
    g.call_after_request.append(func)
    return func


def per_request_callbacks(sender, response):
    for func in getattr(g, 'call_after_request', ()):
        response = func(response)
    return response


# Do this with signals instead of @app.after_request because the session
# cookie is added to the response *after* "after_request" callbacks run.
flask.request_finished.connect(per_request_callbacks, app)
