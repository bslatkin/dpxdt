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
from flask.ext.login import current_user, login_required
from flask.ext.wtf import Form

# Local modules
from . import app
from . import db
from . import login
import auth
import forms
import models


@app.route('/')
def homepage():
    """Renders the homepage."""
    context = {
    }
    return render_template('home.html', **context)


@app.route('/new', methods=['GET', 'POST'])
@login_required
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

    return render_template(
        'new_build.html',
        build_form=form)


@app.route('/build')
@auth.build_access_required
def view_build(build):
    """Page for viewing all releases in a build."""
    candidate_list = (
        models.Release.query
        .filter_by(build_id=build.id)
        .order_by(models.Release.created.desc())
        .all())

    # Collate by release name, order releases by latest creation
    release_dict = {}
    created_dict = {}
    for candidate in candidate_list:
        release_list = release_dict.setdefault(candidate.name, [])
        release_list.append(candidate)

        max_created = created_dict.get(candidate.name, candidate.created)
        created_dict[candidate.name] = max(candidate.created, max_created)

    # Sort each release by candidate number descending
    for release_list in release_dict.itervalues():
        release_list.sort(key=lambda x: x.number, reverse=True)

    # Sort all releases by created time descending
    release_age_list = [
        (value, key) for key, value in created_dict.iteritems()]
    release_age_list.sort(reverse=True)
    release_name_list = [key for _, key in release_age_list]

    # Extract run metadata about each release
    run_stats_dict = {}
    for candidate in candidate_list:
        successful = (
            models.Run.query
            .filter_by(release_id=candidate.id)
            .filter(models.Run.status.in_([
                        models.Run.DIFF_APPROVED, models.Run.DIFF_NOT_FOUND]))
            .count())
        failed = (
            models.Run.query
            .filter_by(release_id=candidate.id, status=models.Run.DIFF_FOUND)
            .count())
        needs_diff = (
            models.Run.query
            .filter_by(release_id=candidate.id, status=models.Run.NEEDS_DIFF)
            .count())
        pending = (
            models.Run.query
            .filter_by(release_id=candidate.id, status=models.Run.DATA_PENDING)
            .count())
        total = pending + needs_diff + successful + failed
        complete = successful + failed

        run_stats_dict[candidate] = (total, complete, successful, failed)

    return render_template(
        'view_build.html',
        build=build,
        release_name_list=release_name_list,
        release_dict=release_dict,
        run_stats_dict=run_stats_dict)


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

    return render_template(
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


@app.route('/run', methods=['GET', 'POST'])
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
            'view_run',
            id=build.id,
            name=release.name,
            number=release.number,
            test=run.name))

    # Find the previous and next runs in this release for easy linking.
    # TODO: Sort this by diff status first, then by name (ones with a diff
    # found should come first).
    previous_run = (
        models.Run.query
        .filter_by(release_id=release.id)
        .filter(models.Run.name < run.name)
        .order_by(models.Run.name.desc())
        .first())

    next_run = (
        models.Run.query
        .filter_by(release_id=release.id)
        .filter(models.Run.name > run.name)
        .order_by(models.Run.name)
        .first())

    # Update form values for rendering
    form.approve.data = True
    form.disapprove.data = True

    return render_template(
        'view_run.html',
        build=build,
        release=release,
        run=run,
        run_form=form,
        previous_run=previous_run,
        next_run=next_run)


@app.route('/image', endpoint='view_image')
@app.route('/log', endpoint='view_log')
@auth.build_access_required
def view_artifact(build):
    """Page for viewing a specific artifact from a test run."""
    build_id = request.args.get('id', type=int)
    release_name = request.args.get('name', type=str)
    release_number = request.args.get('number', type=int)
    run_name = request.args.get('test', type=str)
    file_type = request.args.get('type', type=str)
    if not (build_id and release_name and release_number and
            run_name and file_type):
        abort(400)

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    if not release:
        abort(404)

    run = (
        models.Run.query
        .filter_by(release_id=release.id, name=run_name)
        .first())
    if not run:
        abort(404)

    image_file = False
    log_file = False
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

    if not sha1sum:
        abort(404)

    return render_template(
        'view_artifact.html',
        build=build,
        release=release,
        run=run,
        file_type=file_type,
        image_file=image_file,
        log_file=log_file,
        sha1sum=sha1sum)


@app.route('/static/dummy')
def view_dummy_url():
    return app.send_static_file('dummy/index.html')
