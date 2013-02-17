#!/usr/bin/env python

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
