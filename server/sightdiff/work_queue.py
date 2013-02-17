#!/usr/bin/env python

"""TODO
"""

import datetime
import logging
import time
import uuid

# Local libraries
import flask
from flask import Flask, request

# Environment
import sightdiff
app = sightdiff.app
db = sightdiff.db


class Error(Exception):
  """Base class for exceptions in this module."""

class TaskAlreadyExistsError(Error):
  """Task with the given ID already exists in the queue."""

class TaskDoesNotExistError(Error):
  """Task with the given ID does not exist and cannot be finished."""

class LeaseExpiredError(Error):
  """Owner's lease on the task has expired, not completing task."""

class NotOwnerError(Error):
  """Requestor is no longer the owner of the task."""


class WorkQueue(db.Model):
  """
  """

  task_id = db.Column(db.String(100), primary_key=True)
  queue_name = db.Column(db.String(50), nullable=False)
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
  )


def add(queue_name, payload=None, content_type=None, source=None,
        task_id=None, ignore_tombstones=False):
  """TODO"""
  if task_id:
    task = WorkQueue.query.filter_by(task_id=task_id).first()
    if task:
      if ignore_tombstones:
        return task.task_id
      else:
        raise TaskAlreadyExistsError('queue=%s, task_id=%s' % (
            task_id, queue_name))

  now = datetime.datetime.utcnow()
  task = WorkQueue(
      task_id=uuid.uuid4().hex,
      queue_name=queue_name,
      eta=now,
      source=source,
      payload=payload,
      content_type=content_type)
  db.session.add(task)
  db.session.commit()

  return task.task_id


def _datetime_to_epoch_seconds(dt):
  """TODO"""
  if dt is None:
    return None
  return int(time.mktime(dt.utctimetuple()))


def _task_to_dict(task):
  """TODO"""
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
  """TODO"""
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
  db.session.commit()

  return _task_to_dict(task)


def finish(queue_name, task_id, owner):
  """TODO"""
  now = datetime.datetime.utcnow()
  task = (
      WorkQueue.query
      .filter_by(queue_name=queue_name, task_id=task_id)
      .first())
  if not task:
    raise TaskDoesNotExistError('queue=%s, task_id=%s' % (queue_name, task_id))

  delta = task.eta - now
  if delta < datetime.timedelta(0):
    raise LeaseExpiredError('queue=%s, task_id=%s expired %s' % (
        queue_name, task_id, delta))

  if task.last_owner != owner:
    raise NotOwnerError('queue=%s, task_id=%s, owner=%s' % (
        queue_name, task_id, task.last_owner))

  if not task.live:
    logging.warning('Finishing already dead task. queue=%s, task_id=%s, '
                    'owner=%s', queue_name, task_id, owner)
    return False

  task.live = False
  db.session.add(task)
  db.session.commit()
  return True


@app.route('/api/work_queue/<string:queue_name>/add', methods=['POST'])
def handle_add(queue_name):
  # TODO: Require an API key on the basic auth header

  try:
    task_id = add(
        queue_name,
        payload=request.form.get('payload', type=str),
        content_type=request.form.get('content_type', type=str),
        source=request.form.get('source', request.remote_addr, type=str),
        task_id=request.form.get('task_id', type=str),
        ignore_tombstones=request.form.get('ignore_tombstones', type=bool))
  except Error, e:
    error = '%s: %s' % (e.__class__.__name__, e)
    logging.error('Could not add task request=%r. %s', request, error)
    response = flask.jsonify(error=error)
    response.status_code = 400
    return response

  logging.info('Task added: queue=%s, task_id=%s', queue_name, task_id)
  return flask.jsonify(task_id=task_id)


@app.route('/api/work_queue/<string:queue_name>/lease', methods=['POST'])
def handle_lease(queue_name):
  # TODO: Require an API key on the basic auth header

  task = lease(
      queue_name,
      request.form.get('owner', request.remote_addr, type=str),
      request.form.get('timeout', 60, type=int))

  if not task:
    return flask.jsonify(tasks=[])

  # TODO: If the content_type is JSON, transparently decode and embed it here.

  logging.info('Task leased: queue=%s, task_id=%s',
               queue_name, task['task_id'])
  return flask.jsonify(tasks=[task])


@app.route('/api/work_queue/<string:queue_name>/finish', methods=['POST'])
def handle_finish(queue_name):
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

  return flask.jsonify(success=True)
