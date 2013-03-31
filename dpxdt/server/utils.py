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

import datetime
import logging
import traceback

# Local libraries
import flask

# Local modules
from . import app


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
        flask.abort(jsonify_error(e, status_code=status_code))


def jsonify_error(message_or_exception, status_code=400):
    """Returns a JSON payload that indicates the request had an error."""
    if isinstance(message_or_exception, Exception):
        message = '%s: %s' % (
            message_or_exception.__class__.__name__, message_or_exception)
    else:
        message = message_or_exception

    response = flask.jsonify(error=message)
    response.status_code = status_code
    return response


# From http://flask.pocoo.org/snippets/33/
@app.template_filter()
def timesince(dt, default="just now"):
    """
    Returns string representing "time since" e.g.
    3 days ago, 5 hours ago etc.
    """
    now = datetime.datetime.utcnow()
    diff = now - dt

    periods = (
        (diff.days / 365, "year", "years"),
        (diff.days / 30, "month", "months"),
        (diff.days / 7, "week", "weeks"),
        (diff.days, "day", "days"),
        (diff.seconds / 3600, "hour", "hours"),
        (diff.seconds / 60, "minute", "minutes"),
        (diff.seconds, "second", "seconds"),
    )

    for period, singular, plural in periods:
        if period:
            return "%d %s ago" % (period, singular if period == 1 else plural)

    return default
