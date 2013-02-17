#!/usr/bin/env python

"""Pull-queue API and web handlers."""

import datetime
import json
import logging
import time
import uuid

# Local libraries
import flask
from flask import Flask, request

# Environment
import dpxdt
app = dpxdt.app
db = dpxdt.db


class Error(Exception):
  """Base class for exceptions in this module."""

class TaskDoesNotExistError(Error):
  """Task with the given ID does not exist and cannot be finished."""

class LeaseExpiredError(Error):
  """Owner's lease on the task has expired, not completing task."""

class NotOwnerError(Error):
  """Requestor is no longer the owner of the task."""


class WorkQueue(db.Model):
  """Represents a single item of work to do in a specific queue.

  Queries:
  - By task_id for finishing a task or extending a lease.
  - By Index(queue_name, live, eta) for finding the oldest task for a queue
    that is still pending.
  - By Index(live, create) for finding old tasks that should be deleted from
    the table periodically to free up space.
  """

  task_id = db.Column(db.String(100), primary_key=True, nullable=False)
  queue_name = db.Column(db.String(100), primary_key=True, nullable=False)
  live = db.Column(db.Boolean, default=True, nullable=False)
  eta = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                  nullable=False)

  source = db.Column(db.String)
  created = db.Column(db.DateTime, default=datetime.datetime.utcnow)

  lease_attempts = db.Column(db.Integer, default=0, nullable=False)
  last_owner = db.Column(db.String)
  last_lease = db.Column(db.DateTime, default=datetime.datetime.utcnow)

  payload = db.Column(db.LargeBinary)
  content_type = db.Column(db.String)

  __table_args__ = (
      db.Index('lease_index', 'queue_name', 'live', 'eta'),
      db.Index('reap_index', 'live', 'created'),
  )


def add(queue_name, payload=None, content_type=None,
        source=None, task_id=None):
  """Adds a work item to a queue.

  Args:
    queue_name: Name of the queue to add the work item to.
    payload: Optional. Payload that describes the work to do as a string.
      If not a string and content_type is not provided, then this function
      assumes the payload is a JSON-able Python object.
    content_type: Optional. Content type of the payload.
    source: Optional. Who or what originally created the task.
    task_id: Optional. When supplied, only enqueue this task if a task
      with this ID does not already exist. If a task with this ID already
      exists, then this function will do nothing.

  Returns:
    ID of the task that was added.
  """
  if task_id:
    task = WorkQueue.query.filter_by(task_id=task_id).first()
    if task:
      return task.task_id

  if payload and not content_type  and not isinstance(payload, basestring):
    payload = json.dumps(payload)
    content_type = 'application/json'

  now = datetime.datetime.utcnow()
  task = WorkQueue(
      task_id=uuid.uuid4().hex,
      queue_name=queue_name,
      eta=now,
      source=source,
      payload=payload,
      content_type=content_type)
  db.session.add(task)

  return task.task_id


def _datetime_to_epoch_seconds(dt):
  """Converts a datetime.datetime to seconds since the epoch."""
  if dt is None:
    return None
  return int(time.mktime(dt.utctimetuple()))


def _task_to_dict(task):
  """Converts a WorkQueue to a JSON-able dictionary."""
  return dict(
      task_id=task.task_id,
      queue_name=task.queue_name,
      eta=_datetime_to_epoch_seconds(task.eta),
      source=task.source,
      created=_datetime_to_epoch_seconds(task.created),
      lease_attempts=task.lease_attempts,
      last_lease=_datetime_to_epoch_seconds(task.last_lease),
      payload=task.payload,
      content_type=task.content_type)


def lease(queue_name, owner, timeout):
  """Leases a work item from a queue.

  Args:
    queue_name: Name of the queue to lease work from.
    owner: Who or what is leasing the task.
    timeout: Number of seconds to lock the task for before allowing
      another owner to lease it.

  Returns:
    Dictionary representing the task that was leased, or None if no
    task is available to be leased.
  """
  now = datetime.datetime.utcnow()
  query = (
      WorkQueue.query
      .filter_by(queue_name=queue_name, live=True)
      .filter(WorkQueue.eta <= now))
  task = query.first()
  if not task:
    return None

  task.eta += datetime.timedelta(seconds=timeout)
  task.lease_attempts += 1
  task.last_owner = owner
  task.last_lease = now
  db.session.add(task)

  return _task_to_dict(task)


def finish(queue_name, task_id, owner):
  """Marks a work item on a queue as finished.

  Args:
    queue_name: Name of the queue the work item is on.
    task_id: ID of the task that is finished.
    owner: Who or what has the current lease on the task.

  Returns:
    True if the task has been finished for the first time; False if the
    task was already finished.

  Raises:
    TaskDoesNotExistError if the task does not exist.
    LeaseExpiredError if the lease is no longer active.
    NotOwnerError if the specified owner no longer owns the task.
  """
  now = datetime.datetime.utcnow()
  task = WorkQueue.query.filter_by(queue_name=queue_name,
                                   task_id=task_id).first()
  if not task:
    raise TaskDoesNotExistError('task_id=%s' % task_id)

  delta = task.eta - now
  if delta < datetime.timedelta(0):
    raise LeaseExpiredError('queue=%s, task_id=%s expired %s' % (
        task.queue_name, task_id, delta))

  if task.last_owner != owner:
    raise NotOwnerError('queue=%s, task_id=%s, owner=%s' % (
        task.queue_name, task_id, task.last_owner))

  if not task.live:
    logging.warning('Finishing already dead task. queue=%s, task_id=%s, '
                    'owner=%s', task.queue_name, task_id, owner)
    return False

  task.live = False
  db.session.add(task)
  return True


@app.route('/api/work_queue/<string:queue_name>/add', methods=['POST'])
def handle_add(queue_name):
  """Adds a task to a queue."""
  # TODO: Require an API key on the basic auth header
  try:
    task_id = add(
        queue_name,
        payload=request.form.get('payload', type=str),
        content_type=request.form.get('content_type', type=str),
        source=request.form.get('source', request.remote_addr, type=str),
        task_id=request.form.get('task_id', type=str))
  except Error, e:
    error = '%s: %s' % (e.__class__.__name__, e)
    logging.error('Could not add task request=%r. %s', request, error)
    response = flask.jsonify(error=error)
    response.status_code = 400
    return response

  db.session.commit()
  logging.info('Task added: queue=%s, task_id=%s', queue_name, task_id)
  return flask.jsonify(task_id=task_id)


@app.route('/api/work_queue/<string:queue_name>/lease', methods=['POST'])
def handle_lease(queue_name):
  """Leases a task from a queue."""
  # TODO: Require an API key on the basic auth header
  task = lease(
      queue_name,
      request.form.get('owner', request.remote_addr, type=str),
      request.form.get('timeout', 60, type=int))

  if not task:
    return flask.jsonify(tasks=[])

  if task['payload'] and task['content_type'] == 'application/json':
    task['payload'] = json.loads(task['payload'])

  db.session.commit()
  logging.info('Task leased: queue=%s, task_id=%s',
               queue_name, task['task_id'])
  return flask.jsonify(tasks=[task])


@app.route('/api/work_queue/<string:queue_name>/finish', methods=['POST'])
def handle_finish(queue_name):
  """Marks a task on a queue as finished."""
  # TODO: Require an API key on the basic auth header
  try:
    finish(
        queue_name,
        request.form.get('task_id', type=str),
        request.form.get('owner', request.remote_addr, type=str))
  except Error, e:
    error = '%s: %s' % (e.__class__.__name__, e)
    logging.error('Could not add task request=%r. %s', request, error)
    response = flask.jsonify(error=error)
    response.status_code = 400
    return response

  db.session.commit()
  return flask.jsonify(success=True)
