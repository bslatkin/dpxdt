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

"""Pull-queue API."""

import datetime
import json
import logging
import time
import uuid

# Local modules
from . import app
from . import db
from dpxdt.server import signals


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
    - By Index(queue_name, status, eta) for finding the oldest task for a queue
        that is still pending.
    - By Index(status, create) for finding old tasks that should be deleted
        from the table periodically to free up space.
    """

    CANCELED = 'canceled'
    DONE = 'done'
    ERROR = 'error'
    LIVE = 'live'
    STATES = frozenset([CANCELED, DONE, ERROR, LIVE])

    task_id = db.Column(db.String(100), primary_key=True, nullable=False)
    queue_name = db.Column(db.String(100), primary_key=True, nullable=False)
    status = db.Column(db.Enum(*STATES), default=LIVE, nullable=False)
    eta = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                    nullable=False)

    build_id = db.Column(db.Integer, db.ForeignKey('build.id'))
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'))
    run_id = db.Column(db.Integer, db.ForeignKey('run.id'))

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
        db.Index('created_index', 'queue_name', 'status', 'created'),
        db.Index('lease_index', 'queue_name', 'status', 'eta'),
        db.Index('reap_index', 'status', 'created'),
    )

    @property
    def lease_outstanding(self):
        if not self.status == WorkQueue.LIVE:
            return False
        if not self.last_owner:
            return False
        now = datetime.datetime.utcnow()
        return now < self.eta


def add(queue_name, payload=None, content_type=None, source=None, task_id=None,
        build_id=None, release_id=None, run_id=None):
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
        build_id: Build ID to associate with this task. May be None.
        release_id: Release ID to associate with this task. May be None.
        run_id: Run ID to associate with this task. May be None.

    Returns:
        ID of the task that was added.
    """
    if task_id:
        task = WorkQueue.query.filter_by(task_id=task_id).first()
        if task:
            return task.task_id
    else:
        task_id = uuid.uuid4().hex

    if payload and not content_type and not isinstance(payload, basestring):
        payload = json.dumps(payload)
        content_type = 'application/json'

    now = datetime.datetime.utcnow()
    task = WorkQueue(
        task_id=task_id,
        queue_name=queue_name,
        eta=now,
        source=source,
        build_id=build_id,
        release_id=release_id,
        run_id=run_id,
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
    payload = task.payload
    if payload and task.content_type == 'application/json':
        payload = json.loads(payload)

    return dict(
        task_id=task.task_id,
        queue_name=task.queue_name,
        eta=_datetime_to_epoch_seconds(task.eta),
        source=task.source,
        created=_datetime_to_epoch_seconds(task.created),
        lease_attempts=task.lease_attempts,
        last_lease=_datetime_to_epoch_seconds(task.last_lease),
        payload=payload,
        content_type=task.content_type)


# TODO: Allow requesting key to lease a task if the source matches. This
# would let users run their own workers for server-side capture queues.


def lease(queue_name, owner, count=1, timeout_seconds=60):
    """Leases a work item from a queue, usually the oldest task available.

    Args:
        queue_name: Name of the queue to lease work from.
        owner: Who or what is leasing the task.
        count: Lease up to this many tasks. Return value will never have more
            than this many items present.
        timeout_seconds: Number of seconds to lock the task for before
            allowing another owner to lease it.

    Returns:
        List of dictionaries representing the task that was leased, or
        an empty list if no tasks are available to be leased.
    """
    now = datetime.datetime.utcnow()
    query = (
        WorkQueue.query
        .filter_by(queue_name=queue_name, status=WorkQueue.LIVE)
        .filter(WorkQueue.eta <= now)
        .order_by(WorkQueue.eta)
        .with_lockmode('update')
        .limit(count))

    task_list = query.all()
    if not task_list:
        return None

    next_eta = now + datetime.timedelta(seconds=timeout_seconds)

    for task in task_list:
        task.eta = next_eta
        task.lease_attempts += 1
        task.last_owner = owner
        task.last_lease = now
        task.heartbeat = None
        task.heartbeat_number = 0
        db.session.add(task)

    return [_task_to_dict(task) for task in task_list]


def _get_task_with_policy(queue_name, task_id, owner):
    """Fetches the specified task and enforces ownership policy.

    Args:
        queue_name: Name of the queue the work item is on.
        task_id: ID of the task that is finished.
        owner: Who or what has the current lease on the task.

    Returns:
        The valid WorkQueue task that is currently owned.

    Raises:
        TaskDoesNotExistError if the task does not exist.
        LeaseExpiredError if the lease is no longer active.
        NotOwnerError if the specified owner no longer owns the task.
    """
    now = datetime.datetime.utcnow()
    task = (
        WorkQueue.query
        .filter_by(queue_name=queue_name, task_id=task_id)
        .with_lockmode('update')
        .first())
    if not task:
        raise TaskDoesNotExistError('task_id=%r' % task_id)

    # Lease delta should be positive, meaning it has not yet expired!
    lease_delta = now - task.eta
    if lease_delta > datetime.timedelta(0):
        db.session.rollback()
        raise LeaseExpiredError('queue=%r, task_id=%r expired %s' % (
                                task.queue_name, task_id, lease_delta))

    if task.last_owner != owner:
        db.session.rollback()
        raise NotOwnerError('queue=%r, task_id=%r, owner=%r' % (
                            task.queue_name, task_id, task.last_owner))

    return task


def heartbeat(queue_name, task_id, owner, message, index):
    """Sets the heartbeat status of the task and extends its lease.

    The task's lease is extended by the same amount as its last lease to
    ensure that any operations following the heartbeat will still hold the
    lock for the original lock period.

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

    # Extend the lease by the time of the last lease.
    now = datetime.datetime.utcnow()
    timeout_delta = task.eta - task.last_lease
    task.eta = now + timeout_delta
    task.last_lease = now

    db.session.add(task)

    signals.task_updated.send(app, task=task)

    return True


def finish(queue_name, task_id, owner, error=False):
    """Marks a work item on a queue as finished.

    Args:
        queue_name: Name of the queue the work item is on.
        task_id: ID of the task that is finished.
        owner: Who or what has the current lease on the task.
        error: Defaults to false. True if this task's final state is an error.

    Returns:
        True if the task has been finished for the first time; False if the
        task was already finished.

    Raises:
        TaskDoesNotExistError if the task does not exist.
        LeaseExpiredError if the lease is no longer active.
        NotOwnerError if the specified owner no longer owns the task.
    """
    task = _get_task_with_policy(queue_name, task_id, owner)

    if not task.status == WorkQueue.LIVE:
        logging.warning('Finishing already dead task. queue=%r, task_id=%r, '
                        'owner=%r, status=%r',
                        task.queue_name, task_id, owner, task.status)
        return False

    if not error:
        task.status = WorkQueue.DONE
    else:
        task.status = WorkQueue.ERROR

    task.finished = datetime.datetime.utcnow()
    db.session.add(task)

    signals.task_updated.send(app, task=task)

    return True


def _query(queue_name=None, build_id=None, release_id=None, run_id=None,
           count=None):
    """Queries for work items based on their criteria.

    Args:
        queue_name: Optional queue name to restrict to.
        build_id: Optional build ID to restrict to.
        release_id: Optional release ID to restrict to.
        run_id: Optional run ID to restrict to.
        count: How many tasks to fetch. Defaults to None, which means all
            tasks are fetch that match the query.

    Returns:
        List of WorkQueue items.
    """
    assert queue_name or build_id or release_id or run_id

    q = WorkQueue.query
    if queue_name:
        q = q.filter_by(queue_name=queue_name)
    if build_id:
        q = q.filter_by(build_id=build_id)
    if release_id:
        q = q.filter_by(release_id=release_id)
    if run_id:
        q = q.filter_by(run_id=run_id)

    q = q.order_by(WorkQueue.created.desc())

    if count is not None:
        q = q.limit(count)

    return q.all()


def query(**kwargs):
    """Queries for work items based on their criteria.

    Args:
        queue_name: Optional queue name to restrict to.
        build_id: Optional build ID to restrict to.
        release_id: Optional release ID to restrict to.
        run_id: Optional run ID to restrict to.
        count: How many tasks to fetch. Defaults to None, which means all
            tasks are fetch that match the query.

    Returns:
        Dictionaries of the most recent tasks that match the criteria, in
        order of most recently created. When count is 1 the return value will
        be the most recent task or None. When count is not 1 the return value
        will be a  list of tasks.
    """
    count = kwargs.get('count', None)
    task_list = _query(**kwargs)
    task_dict_list = [_task_to_dict(task) for task in task_list]

    if count == 1:
        if not task_dict_list:
            return None
        else:
            return task_dict_list[0]

    return task_dict_list


def cancel(**kwargs):
    """Cancels work items based on their criteria.

    Args:
        **kwargs: Same parameters as the query() method.

    Returns:
        The number of tasks that were canceled.
    """
    task_list = _query(**kwargs)
    for task in task_list:
        task.status = WorkQueue.CANCELED
        task.finished = datetime.datetime.utcnow()
        db.session.add(task)
    return len(task_list)
