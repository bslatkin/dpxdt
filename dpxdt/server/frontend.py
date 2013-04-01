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

import logging

# Local libraries
import flask
from flask import Flask, abort, redirect, render_template, request, url_for
from flask.ext.wtf import Form

# Local modules
from . import app
from . import db
import forms
import models


@app.route('/')
def homepage():
    context = {
    }
    return render_template('home.html', **context)



@app.route('/new', methods=['GET', 'POST'])
def new_build():
    """Page for crediting or editing a build."""
    form = forms.BuildForm()
    if form.validate_on_submit():
        build = models.Build()
        form.populate_obj(build)
        db.session.add(build)
        db.session.commit()

        logging.info('Created build via UI: build_id=%r, name=%r',
                     build.id, build.name)
        return redirect(url_for('view_build', id=build.id))

    return render_template(
        'new_build.html',
        build_form=form)


@app.route('/build')
def view_build():
    build_id = request.args.get('id', type=int)
    if not build_id:
        return abort(400)

    build = models.Build.query.get(build_id)
    if not build:
        return abort(404)

    candidate_list = (
        models.Release.query
        .filter_by(build_id=build_id)
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


@app.route('/release')
def view_release():
    build_id = request.args.get('id', type=int)
    release_name = request.args.get('name', type=str)
    release_number = request.args.get('number', type=int)
    if not (build_id and release_name and release_number):
        return abort(400)

    build = models.Build.query.get(build_id)
    if not build:
        return abort(404)

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    if not release:
        return abort(404)

    run_list = (
        models.Run.query
        .filter_by(release_id=release.id)
        .order_by(models.Run.name)
        .all())

    # Sort errors first, then by name
    def sort(run):
        if run.DIFF_FOUND:
            return (0, run.name)
        return (1, run.name)

    run_list.sort(key=sort)

    total, complete, successful, failed = classify_runs(run_list)

    newest_run_time = None
    if run_list:
        newest_run_time = max(run.modified for run in run_list)

    return render_template(
        'view_release.html',
        build=build,
        release=release,
        run_list=run_list,
        runs_total=total,
        runs_complete=complete,
        runs_successful=successful,
        runs_failed=failed,
        newest_run_time=newest_run_time)


@app.route('/run')
def view_run():
    build_id = request.args.get('id', type=int)
    release_name = request.args.get('name', type=str)
    release_number = request.args.get('number', type=int)
    run_name = request.args.get('path', type=str)
    if not (build_id and release_name and release_number and run_name):
        return abort(400)

    build = models.Build.query.get(build_id)
    if not build:
        return abort(404)

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    if not release:
        return abort(404)

    run = (
        models.Run.query
        .filter_by(release_id=release.id, name=run_name)
        .first())
    if not run:
        return abort(404)

    return render_template(
        'view_run.html',
        build=build,
        release=release,
        run=run)


@app.route('/image')
def view_image():
    build_id = request.args.get('id', type=int)
    release_name = request.args.get('name', type=str)
    release_number = request.args.get('number', type=int)
    run_name = request.args.get('path', type=str)
    image_type = request.args.get('type', type=str)
    if not (build_id and release_name and release_number and
            run_name and image_type):
        return abort(400)

    # TODO: Make this reusable
    build = models.Build.query.get(build_id)
    if not build:
        return abort(404)

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    if not release:
        return abort(404)

    run = (
        models.Run.query
        .filter_by(release_id=release.id, name=run_name)
        .first())
    if not run:
        return abort(404)

    if image_type == 'before':
        sha1sum = run.ref_image
    elif image_type == 'diff':
        sha1sum = run.diff_image
    elif image_type == 'after':
        sha1sum = run.image
    else:
        return abort(400)

    if not sha1sum:
        return abort(404)

    return render_template(
        'view_image.html',
        build=build,
        release=release,
        run=run,
        image_type=image_type,
        sha1sum=sha1sum)


@app.route('/log')
def view_log():
    return
