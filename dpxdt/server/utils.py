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

import logging
import traceback

# Local libraries
import flask


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
