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

"""Pull-queue API and web handlers."""

import datetime
import json
import logging
import time
import uuid

# Local libraries
import flask
from flask import Flask, render_template, request

# Local modules
from . import app
from . import db
import auth
import utils


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

    source = db.Column(db.String(500))
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    finished = db.Column(db.DateTime)

    lease_attempts = db.Column(db.Integer, default=0, nullable=False)
    last_lease = db.Column(db.DateTime)
    last_owner = db.Column(db.String(500))

    heartbeat = db.Column(db.Text)
    heartbeat_number = db.Column(db.Integer)

    payload = db.Column(db.LargeBinary)
    content_type = db.Column(db.String(100))

    __table_args__ = (
        db.Index('lease_index', 'queue_name', 'live', 'eta'),
        db.Index('reap_index', 'live', 'created'),
    )

    @property
    def lease_outstanding(self):
        if not self.live:
            return False
        if not self.last_owner:
            return False
        now = datetime.datetime.utcnow()
        return now < self.eta


def add(queue_name, payload=None, content_type=None,
        source=None, task_id=None):
    """Adds a work item to a queue.

    Args:
        queue_name: Name of the queue to add the work item to.
        payload: Optional. Payload that describes the work to do as a string.
            If not a string and content_type is not provided, then this
            function assumes the payload is a JSON-able Python object.
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

    if payload and not content_type    and not isinstance(payload, basestring):
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
    """Leases a work item from a queue, usually the oldest task available.

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
        .filter(WorkQueue.eta <= now)
        .order_by(WorkQueue.eta))
    task = query.first()
    if not task:
        return None

    task.eta = now + datetime.timedelta(seconds=timeout)
    task.lease_attempts += 1
    task.last_owner = owner
    task.last_lease = now
    task.heartbeat = None
    task.heartbeat_number = 0
    db.session.add(task)

    return _task_to_dict(task)


def _get_task_with_policy(queue_name, task_id, owner):
    """Fetches the specified task and enforces ownership policy.

    Args:
        queue_name: Name of the queue the work item is on.
        task_id: ID of the task that is finished.
        owner: Who or what has the current lease on the task.
        before_expiration: When True, assert that we are before the task lease
            has expired. When False, assert that we are after the lease
            has expired. Use False when acquiring a new lease, and True
            when asserting an existing lease.

    Returns:
        The valid WorkQueue task that is currently owned.

    Raises:
        TaskDoesNotExistError if the task does not exist.
        LeaseExpiredError if the lease is no longer active.
        NotOwnerError if the specified owner no longer owns the task.
    """
    now = datetime.datetime.utcnow()
    task = WorkQueue.query.filter_by(
        queue_name=queue_name,
        task_id=task_id).first()
    if not task:
        raise TaskDoesNotExistError('task_id=%r' % task_id)

    # Lease delta should be positive, meaning it has not yet expired!
    lease_delta = now - task.eta
    if lease_delta > datetime.timedelta(0):
        raise LeaseExpiredError('queue=%r, task_id=%r expired %s' % (
                                task.queue_name, task_id, lease_delta))

    if task.last_owner != owner:
        raise NotOwnerError('queue=%r, task_id=%r, owner=%r' % (
                            task.queue_name, task_id, task.last_owner))

    return task


def heartbeat(queue_name, task_id, owner, message, index):
    """Sets the heartbeat status of the task.

    Args:
        queue_name: Name of the queue the work item is on.
        task_id: ID of the task that is finished.
        owner: Who or what has the current lease on the task.
        message: Message to report as the task's current status.
        index: Number of this message in the sequence of messages from the
            current task owner, starting at zero. This lets the API receive
            heartbeats out of order, yet ensure that the most recent message
            is actually saved to the database. This requires the owner issuing
            heartbeat messages to issue heartbeat indexes sequentially.

    Returns:
        True if the heartbeat message was set, False if it is lower than the
        current heartbeat index.

    Raises:
        TaskDoesNotExistError if the task does not exist.
        LeaseExpiredError if the lease is no longer active.
        NotOwnerError if the specified owner no longer owns the task.
    """
    task = _get_task_with_policy(queue_name, task_id, owner)
    if task.heartbeat_number > index:
        return False

    task.heartbeat = message
    task.heartbeat_number = index
    db.session.add(task)
    return True


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
    task = _get_task_with_policy(queue_name, task_id, owner)

    if not task.live:
        logging.warning('Finishing already dead task. queue=%r, task_id=%r, '
                        'owner=%r', task.queue_name, task_id, owner)
        return False

    task.live = False
    task.finished = datetime.datetime.utcnow()
    db.session.add(task)
    return True


@app.route('/api/work_queue/<string:queue_name>/add', methods=['POST'])
@auth.superuser_api_key_required
def handle_add(queue_name):
    """Adds a task to a queue."""
    source = request.form.get('source', request.remote_addr, type=str)
    try:
        task_id = add(
            queue_name,
            payload=request.form.get('payload', type=str),
            content_type=request.form.get('content_type', type=str),
            source=source,
            task_id=request.form.get('task_id', type=str))
    except Error, e:
        return utils.jsonify_error(e)

    db.session.commit()
    logging.info('Task added: queue=%r, task_id=%r, source=%r',
                 queue_name, task_id, source)
    return flask.jsonify(task_id=task_id)


@app.route('/api/work_queue/<string:queue_name>/lease', methods=['POST'])
@auth.superuser_api_key_required
def handle_lease(queue_name):
    """Leases a task from a queue."""
    owner = request.form.get('owner', request.remote_addr, type=str)
    try:
        task = lease(
            queue_name,
            owner,
            request.form.get('timeout', 60, type=int))
    except Error, e:
        return utils.jsonify_error(e)

    if not task:
        return flask.jsonify(tasks=[])

    if task['payload'] and task['content_type'] == 'application/json':
        task['payload'] = json.loads(task['payload'])

    db.session.commit()
    logging.debug('Task leased: queue=%r, task_id=%r, owner=%r',
                  queue_name, task['task_id'], owner)
    return flask.jsonify(tasks=[task])


@app.route('/api/work_queue/<string:queue_name>/heartbeat', methods=['POST'])
@auth.superuser_api_key_required
def handle_heartbeat(queue_name):
    """Updates the heartbeat message for a task."""
    task_id = request.form.get('task_id', type=str)
    message = request.form.get('message', type=str)
    index = request.form.get('index', type=int)
    try:
        heartbeat(
            queue_name,
            task_id,
            request.form.get('owner', request.remote_addr, type=str),
            message,
            index)
    except Error, e:
        return utils.jsonify_error(e)

    db.session.commit()
    logging.debug('Task heartbeat: queue=%r, task_id=%r, message=%r, index=%d',
                  queue_name, task_id, message, index)
    return flask.jsonify(success=True)


@app.route('/api/work_queue/<string:queue_name>/finish', methods=['POST'])
@auth.superuser_api_key_required
def handle_finish(queue_name):
    """Marks a task on a queue as finished."""
    task_id = request.form.get('task_id', type=str)
    owner = request.form.get('owner', request.remote_addr, type=str)
    try:
        finish(queue_name, task_id, owner)
    except Error, e:
        return utils.jsonify_error(e)

    db.session.commit()
    logging.debug('Task finished: queue=%r, task_id=%r, owner=%r',
                  queue_name, task_id, owner)
    return flask.jsonify(success=True)


# TODO: Add an index page that shows all possible work queues


@app.route('/api/work_queue/<string:queue_name>')
@auth.superuser_required
def manage_work_queue(queue_name):
    """Page for viewing the contents of a work queue."""
    query = (
        WorkQueue.query
        .filter_by(queue_name=queue_name)
        .order_by(WorkQueue.eta)
        .limit(1000))
    context = dict(
        queue_name=queue_name,
        work_list=list(query)
    )
    return render_template('view_work_queue.html', **context)
