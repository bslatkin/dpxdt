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

"""Frontend for the API server."""

import functools
import logging

# Local libraries
import flask
from flask import Flask, abort, redirect, render_template, request, url_for
from flask.ext.login import (
    current_user, fresh_login_required, login_fresh, login_required)
from flask.ext.wtf import Form
import sqlalchemy

# Local modules
from . import app
from . import db
from . import login
import auth
import forms
import models


def _render_template_with_defaults(template_path, **context):
    """Renders the template with some extra context"""
    context.setdefault('current_user', current_user)
    return render_template(template_path, **context)


@app.route('/')
def homepage():
    """Renders the homepage."""
    build_list = list(
        models.Build.query
        .filter_by(public=True)
        .order_by(models.Build.created.desc())
        .limit(1000))

    if current_user.is_authenticated():
        if not login_fresh():
            logging.debug('User needs a fresh token')
            abort(login.needs_refresh())

        auth.claim_invitations(current_user)

        # List builds you own first, followed by public ones.
        # TODO: Cache this list
        db.session.add(current_user)
        build_list = list(
            current_user.builds
            .order_by(models.Build.created.desc())
            .limit(1000)) + build_list

    return _render_template_with_defaults(
        'home.html',
        build_list=build_list)


@app.route('/new', methods=['GET', 'POST'])
@fresh_login_required
def new_build():
    """Page for crediting or editing a build."""
    form = forms.BuildForm()
    if form.validate_on_submit():
        build = models.Build()
        form.populate_obj(build)
        build.owners.append(current_user)
        db.session.add(build)
        db.session.commit()

        logging.info('Created build via UI: build_id=%r, name=%r',
                     build.id, build.name)
        return redirect(url_for('view_build', id=build.id))

    return _render_template_with_defaults(
        'new_build.html',
        build_form=form)


@app.route('/build')
@auth.build_access_required
def view_build(build):
    """Page for viewing all releases in a build."""
    page_size = 20
    offset = request.args.get('offset', 0, type=int)
    candidate_list = list(
        models.Release.query
        .filter_by(build_id=build.id)
        .order_by(models.Release.created.desc())
        .offset(offset)
        .limit(page_size + 1))

    has_next_page = len(candidate_list) > page_size
    if has_next_page:
        candidate_list = candidate_list[:-1]

    # Collate by release name, order releases by latest creation. Init stats.
    release_dict = {}
    created_dict = {}
    run_stats_dict = {}
    for candidate in candidate_list:
        release_list = release_dict.setdefault(candidate.name, [])
        release_list.append(candidate)

        max_created = created_dict.get(candidate.name, candidate.created)

        created_dict[candidate.name] = max(candidate.created, max_created)

        run_stats_dict[candidate.id] = dict(
            runs_total=0,
            runs_complete=0,
            runs_successful=0,
            runs_failed=0)

    # Sort each release by candidate number descending
    for release_list in release_dict.itervalues():
        release_list.sort(key=lambda x: x.number, reverse=True)

    # Sort all releases by created time descending
    release_age_list = [
        (value, key) for key, value in created_dict.iteritems()]
    release_age_list.sort(reverse=True)
    release_name_list = [key for _, key in release_age_list]

    # Extract run metadata about each release
    stats_counts = list(
        db.session.query(
            models.Run.release_id,
            models.Run.status,
            sqlalchemy.func.count(models.Run.id))
        .join(models.Release)
        .filter(models.Release.id.in_(run_stats_dict.keys()))
        .group_by(models.Run.status, models.Run.release_id))

    for candidate_id, status, count in stats_counts:
        stats_dict = run_stats_dict[candidate_id]
        stats_dict['runs_total'] += count

        if status in (models.Run.DIFF_APPROVED, models.Run.DIFF_NOT_FOUND):
            stats_dict['runs_successful'] += count
            stats_dict['runs_complete'] += count
        elif status == models.Run.DIFF_FOUND:
            stats_dict['runs_failed'] += count
            stats_dict['runs_complete'] += count

    return _render_template_with_defaults(
        'view_build.html',
        build=build,
        release_name_list=release_name_list,
        release_dict=release_dict,
        run_stats_dict=run_stats_dict,
        has_next_page=has_next_page,
        current_offset=offset,
        next_offset=offset + page_size,
        last_offset=max(0, offset -  page_size))


def classify_runs(run_list):
    """Returns (total, complete, succesful, failed) for the given Runs."""
    total, successful, failed = 0, 0, 0
    for run in run_list:
        if run.status in (models.Run.DIFF_APPROVED, models.Run.DIFF_NOT_FOUND):
            successful += 1
            total += 1
        elif run.status == models.Run.DIFF_FOUND:
            failed += 1
            total += 1
        elif run.status in (models.Run.NEEDS_DIFF, models.Run.DATA_PENDING):
            total += 1

    complete = successful + failed
    return total, complete, successful, failed


@app.route('/release', methods=['GET', 'POST'])
@auth.build_access_required
def view_release(build):
    """Page for viewing all tests runs in a release."""
    if request.method == 'POST':
        form = forms.ReleaseForm(request.form)
    else:
        form = forms.ReleaseForm(request.args)

    form.validate()

    release = (
        models.Release.query
        .filter_by(
            build_id=build.id,
            name=form.name.data,
            number=form.number.data)
        .first())
    if not release:
        abort(404)

    if request.method == 'POST':
        decision_states = (
            models.Release.REVIEWING, models.Release.RECEIVING)

        if form.good.data and release.status in decision_states:
            release.status = models.Release.GOOD
        elif form.bad.data and release.status in decision_states:
            release.status = models.Release.BAD
        elif form.reviewing.data and release.status in (
                models.Release.GOOD, models.Release.BAD):
            release.status = models.Release.REVIEWING
        else:
            logging.warning(
                'Bad state transition for name=%r, number=%r, form=%r',
                release.name, release.number, form.data)
            abort(400)

        db.session.add(release)
        db.session.commit()

        return redirect(url_for(
            'view_release',
            id=build.id,
            name=release.name,
            number=release.number))

    run_list = (
        models.Run.query
        .filter_by(release_id=release.id)
        .order_by(models.Run.name)
        .all())

    # Sort errors first, then by name
    def sort(run):
        if run.status == models.Run.DIFF_FOUND:
            return (0, run.name)
        return (1, run.name)

    run_list.sort(key=sort)

    total, complete, successful, failed = classify_runs(run_list)

    newest_run_time = None
    if run_list:
        newest_run_time = max(run.modified for run in run_list)

    # Update form values for rendering
    form.good.data = True
    form.bad.data = True
    form.reviewing.data = True

    return _render_template_with_defaults(
        'view_release.html',
        build=build,
        release=release,
        run_list=run_list,
        runs_total=total,
        runs_complete=complete,
        runs_successful=successful,
        runs_failed=failed,
        newest_run_time=newest_run_time,
        release_form=form)


def _get_artifact_context(run, file_type):
    """Gets the artifact details for the given run and file_type."""
    sha1sum = None
    image_file = False
    log_file = False
    config_file = False

    if request.path == '/image':
        image_file = True
        if file_type == 'before':
            sha1sum = run.ref_image
        elif file_type == 'diff':
            sha1sum = run.diff_image
        elif file_type == 'after':
            sha1sum = run.image
        else:
            abort(400)
    elif request.path == '/log':
        log_file = True
        if file_type == 'before':
            sha1sum = run.ref_log
        elif file_type == 'diff':
            sha1sum = run.diff_log
        elif file_type == 'after':
            sha1sum = run.log
        else:
            abort(400)
    elif request.path == '/config':
        config_file = True
        if file_type == 'before':
            sha1sum = run.ref_config
        elif file_type == 'after':
            sha1sum = run.config
        else:
            abort(400)

    return image_file, log_file, config_file, sha1sum


@app.route('/run', methods=['GET', 'POST'])
@app.route('/image', endpoint='view_image', methods=['GET', 'POST'])
@app.route('/log', endpoint='view_log', methods=['GET', 'POST'])
@app.route('/config', endpoint='view_config', methods=['GET', 'POST'])
@auth.build_access_required
def view_run(build):
    """Page for viewing before/after for a specific test run."""
    if request.method == 'POST':
        form = forms.RunForm(request.form)
    else:
        form = forms.RunForm(request.args)

    form.validate()

    release = (
        models.Release.query
        .filter_by(
            build_id=build.id,
            name=form.name.data,
            number=form.number.data)
        .first())
    if not release:
        abort(404)

    run = (
        models.Run.query
        .filter_by(release_id=release.id, name=form.test.data)
        .first())
    if not run:
        abort(404)

    file_type = form.type.data
    image_file, log_file, config_file, sha1sum = (
        _get_artifact_context(run, file_type))

    if request.method == 'POST':
        if form.approve.data and run.status == models.Run.DIFF_FOUND:
            run.status = models.Run.DIFF_APPROVED
        elif form.disapprove.data and run.status == models.Run.DIFF_APPROVED:
            run.status = models.Run.DIFF_FOUND
        else:
            abort(400)

        db.session.add(run)
        db.session.commit()

        return redirect(url_for(
            request.endpoint,
            id=build.id,
            name=release.name,
            number=release.number,
            test=run.name,
            type=file_type))

    # We sort the runs in the release by diffs first, then by name. Simulate
    # that behavior here with multiple queries.
    previous_run = None
    next_run = None
    if run.status == models.Run.DIFF_FOUND:
        previous_run = (
            models.Run.query
            .filter_by(release_id=release.id)
            .filter(models.Run.status == models.Run.DIFF_FOUND)
            .filter(models.Run.name < run.name)
            .order_by(models.Run.name.desc())
            .first())
        next_run = (
            models.Run.query
            .filter_by(release_id=release.id)
            .filter(models.Run.status == models.Run.DIFF_FOUND)
            .filter(models.Run.name > run.name)
            .order_by(models.Run.name)
            .first())

        if not next_run:
            next_run = (
                models.Run.query
                .filter_by(release_id=release.id)
                .filter(models.Run.status != models.Run.DIFF_FOUND)
                .order_by(models.Run.name)
                .first())
    else:
        previous_run = (
            models.Run.query
            .filter_by(release_id=release.id)
            .filter(models.Run.status != models.Run.DIFF_FOUND)
            .filter(models.Run.name < run.name)
            .order_by(models.Run.name.desc())
            .first())
        next_run = (
            models.Run.query
            .filter_by(release_id=release.id)
            .filter(models.Run.status != models.Run.DIFF_FOUND)
            .filter(models.Run.name > run.name)
            .order_by(models.Run.name)
            .first())

        if not previous_run:
            previous_run = (
                models.Run.query
                .filter_by(release_id=release.id)
                .filter(models.Run.status == models.Run.DIFF_FOUND)
                .order_by(models.Run.name.desc())
                .first())

    # Update form values for rendering
    form.approve.data = True
    form.disapprove.data = True

    context = dict(
        build=build,
        release=release,
        run=run,
        run_form=form,
        previous_run=previous_run,
        next_run=next_run,
        file_type=file_type,
        image_file=image_file,
        log_file=log_file,
        config_file=config_file,
        sha1sum=sha1sum)

    if file_type:
        template_name = 'view_artifact.html'
    else:
        template_name = 'view_run.html'

    return _render_template_with_defaults(template_name, **context)


@app.route('/static/dummy')
def view_dummy_url():
    return app.send_static_file('dummy/index.html')
