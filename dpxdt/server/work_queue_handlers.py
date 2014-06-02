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

"""Pull-queue web handlers."""

import logging

# Local libraries
import flask
from flask import Flask, redirect, render_template, request, url_for
from sqlalchemy import func

# Local modules
from . import app
from . import db
from dpxdt.server import auth
from dpxdt.server import forms
from dpxdt.server import utils
from dpxdt.server import work_queue


@app.route('/api/work_queue/<string:queue_name>/add', methods=['POST'])
@auth.superuser_api_key_required
@utils.retryable_transaction()
def handle_add(queue_name):
    """Adds a task to a queue."""
    source = request.form.get('source', request.remote_addr, type=str)
    try:
        task_id = work_queue.add(
            queue_name,
            payload=request.form.get('payload', type=str),
            content_type=request.form.get('content_type', type=str),
            source=source,
            task_id=request.form.get('task_id', type=str))
    except work_queue.Error, e:
        return utils.jsonify_error(e)

    db.session.commit()
    logging.info('Task added: queue=%r, task_id=%r, source=%r',
                 queue_name, task_id, source)
    return flask.jsonify(task_id=task_id)


@app.route('/api/work_queue/<string:queue_name>/lease', methods=['POST'])
@auth.superuser_api_key_required
@utils.retryable_transaction()
def handle_lease(queue_name):
    """Leases a task from a queue."""
    owner = request.form.get('owner', request.remote_addr, type=str)
    try:
        task_list = work_queue.lease(
            queue_name,
            owner,
            request.form.get('count', 1, type=int),
            request.form.get('timeout', 60, type=int))
    except work_queue.Error, e:
        return utils.jsonify_error(e)

    if not task_list:
        return flask.jsonify(tasks=[])

    db.session.commit()
    task_ids = [t['task_id'] for t in task_list]
    logging.debug('Task leased: queue=%r, task_ids=%r, owner=%r',
                  queue_name, task_ids, owner)
    return flask.jsonify(tasks=task_list)


@app.route('/api/work_queue/<string:queue_name>/heartbeat', methods=['POST'])
@auth.superuser_api_key_required
@utils.retryable_transaction()
def handle_heartbeat(queue_name):
    """Updates the heartbeat message for a task."""
    task_id = request.form.get('task_id', type=str)
    message = request.form.get('message', type=str)
    index = request.form.get('index', type=int)
    try:
        work_queue.heartbeat(
            queue_name,
            task_id,
            request.form.get('owner', request.remote_addr, type=str),
            message,
            index)
    except work_queue.Error, e:
        return utils.jsonify_error(e)

    db.session.commit()
    logging.debug('Task heartbeat: queue=%r, task_id=%r, message=%r, index=%d',
                  queue_name, task_id, message, index)
    return flask.jsonify(success=True)


@app.route('/api/work_queue/<string:queue_name>/finish', methods=['POST'])
@auth.superuser_api_key_required
@utils.retryable_transaction()
def handle_finish(queue_name):
    """Marks a task on a queue as finished."""
    task_id = request.form.get('task_id', type=str)
    owner = request.form.get('owner', request.remote_addr, type=str)
    error = request.form.get('error', type=str) is not None
    try:
        work_queue.finish(queue_name, task_id, owner, error=error)
    except work_queue.Error, e:
        return utils.jsonify_error(e)

    db.session.commit()
    logging.debug('Task finished: queue=%r, task_id=%r, owner=%r, error=%r',
                  queue_name, task_id, owner, error)
    return flask.jsonify(success=True)


@app.route('/api/work_queue')
@auth.superuser_required
def view_all_work_queues():
    """Page for viewing the index of all active work queues."""
    count_list = list(
        db.session.query(
            work_queue.WorkQueue.queue_name,
            work_queue.WorkQueue.status,
            func.count(work_queue.WorkQueue.task_id))
        .group_by(work_queue.WorkQueue.queue_name,
                  work_queue.WorkQueue.status))

    queue_dict = {}
    for name, status, count in count_list:
        queue_dict[(name, status)] = dict(
            name=name, status=status, count=count)

    max_created_list = list(
        db.session.query(
            work_queue.WorkQueue.queue_name,
            work_queue.WorkQueue.status,
            func.max(work_queue.WorkQueue.created))
        .group_by(work_queue.WorkQueue.queue_name,
                  work_queue.WorkQueue.status))

    for name, status, newest_created in max_created_list:
        queue_dict[(name, status)]['newest_created'] = newest_created

    min_eta_list = list(
        db.session.query(
            work_queue.WorkQueue.queue_name,
            work_queue.WorkQueue.status,
            func.min(work_queue.WorkQueue.eta))
        .group_by(work_queue.WorkQueue.queue_name,
                  work_queue.WorkQueue.status))

    for name, status, oldest_eta in min_eta_list:
        queue_dict[(name, status)]['oldest_eta'] = oldest_eta

    queue_list = list(queue_dict.values())
    queue_list.sort(key=lambda x: (x['name'], x['status']))

    context = dict(
        queue_list=queue_list,
    )
    return render_template('view_work_queue_index.html', **context)


@app.route('/api/work_queue/<string:queue_name>', methods=['GET', 'POST'])
@auth.superuser_required
def manage_work_queue(queue_name):
    """Page for viewing the contents of a work queue."""
    modify_form = forms.ModifyWorkQueueTaskForm()
    if modify_form.validate_on_submit():
        primary_key = (modify_form.task_id.data, queue_name)
        task = work_queue.WorkQueue.query.get(primary_key)
        if task:
            logging.info('Action: %s task_id=%r',
                         modify_form.action.data, modify_form.task_id.data)
            if modify_form.action.data == 'retry':
                task.status = work_queue.WorkQueue.LIVE
                task.lease_attempts = 0
                task.heartbeat = 'Retrying ...'
                db.session.add(task)
            else:
                db.session.delete(task)
            db.session.commit()
        else:
            logging.warning('Could not find task_id=%r to delete',
                            modify_form.task_id.data)
        return redirect(url_for('manage_work_queue', queue_name=queue_name))

    query = (
        work_queue.WorkQueue.query
        .filter_by(queue_name=queue_name)
        .order_by(work_queue.WorkQueue.created.desc()))

    status = request.args.get('status', '', type=str).lower()
    if status in work_queue.WorkQueue.STATES:
        query = query.filter_by(status=status)
    else:
        status = None

    item_list = list(query.limit(100))
    work_list = []
    for item in item_list:
        form = forms.ModifyWorkQueueTaskForm()
        form.task_id.data = item.task_id
        form.delete.data = True
        work_list.append((item, form))

    context = dict(
        queue_name=queue_name,
        status=status,
        work_list=work_list,
    )
    return render_template('view_work_queue.html', **context)
