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

import base64
import datetime
import hashlib
import logging

# Local libraries
import flask
from flask import Flask, abort, g, redirect, render_template, request, url_for
from flask.ext.login import (
    current_user, fresh_login_required, login_fresh, login_required)
from flask.ext.wtf import Form

# Local modules
from . import app
from . import db
from . import login
from dpxdt.server import auth
from dpxdt.server import forms
from dpxdt.server import models
from dpxdt.server import operations
from dpxdt.server import signals
from dpxdt.server import utils


@app.context_processor
def frontend_context():
    """Adds extra default context for rendered templates."""
    return dict(cache_buster=utils.get_deployment_timestamp())


@app.route('/')
def homepage():
    """Renders the homepage."""
    if current_user.is_authenticated():
        if not login_fresh():
            logging.debug('User needs a fresh token')
            abort(login.needs_refresh())

        auth.claim_invitations(current_user)

    build_list = operations.UserOps(current_user.get_id()).get_builds()

    return render_template(
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
        db.session.flush()

        auth.save_admin_log(build, created_build=True, message=build.name)

        db.session.commit()

        operations.UserOps(current_user.get_id()).evict()

        logging.info('Created build via UI: build_id=%r, name=%r',
                     build.id, build.name)
        return redirect(url_for('view_build', id=build.id))

    return render_template(
        'new_build.html',
        build_form=form)


@app.route('/build')
@auth.build_access_required
def view_build():
    """Page for viewing all releases in a build."""
    build = g.build
    page_size = 20
    offset = request.args.get('offset', 0, type=int)

    ops = operations.BuildOps(build.id)
    has_next_page, candidate_list, stats_counts = ops.get_candidates(
        page_size, offset)

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
            runs_failed=0,
            runs_baseline=0,
            runs_pending=0)

    # Sort each release by candidate number descending
    for release_list in release_dict.itervalues():
        release_list.sort(key=lambda x: x.number, reverse=True)

    # Sort all releases by created time descending
    release_age_list = [
        (value, key) for key, value in created_dict.iteritems()]
    release_age_list.sort(reverse=True)
    release_name_list = [key for _, key in release_age_list]

    # Count totals for each run state within that release.
    for candidate_id, status, count in stats_counts:
        stats_dict = run_stats_dict[candidate_id]
        for key in ops.get_stats_keys(status):
            stats_dict[key] += count

    return render_template(
        'view_build.html',
        build=build,
        release_name_list=release_name_list,
        release_dict=release_dict,
        run_stats_dict=run_stats_dict,
        has_next_page=has_next_page,
        current_offset=offset,
        next_offset=offset + page_size,
        last_offset=max(0, offset -  page_size))


@app.route('/release', methods=['GET', 'POST'])
@auth.build_access_required
def view_release():
    """Page for viewing all tests runs in a release."""
    build = g.build
    if request.method == 'POST':
        form = forms.ReleaseForm(request.form)
    else:
        form = forms.ReleaseForm(request.args)

    form.validate()

    ops = operations.BuildOps(build.id)
    release, run_list, stats_dict, approval_log = ops.get_release(
        form.name.data, form.number.data)

    if not release:
        abort(404)

    if request.method == 'POST':
        decision_states = (
            models.Release.REVIEWING,
            models.Release.RECEIVING,
            models.Release.PROCESSING)

        if form.good.data and release.status in decision_states:
            release.status = models.Release.GOOD
            auth.save_admin_log(build, release_good=True, release=release)
        elif form.bad.data and release.status in decision_states:
            release.status = models.Release.BAD
            auth.save_admin_log(build, release_bad=True, release=release)
        elif form.reviewing.data and release.status in (
                models.Release.GOOD, models.Release.BAD):
            release.status = models.Release.REVIEWING
            auth.save_admin_log(build, release_reviewing=True, release=release)
        else:
            logging.warning(
                'Bad state transition for name=%r, number=%r, form=%r',
                release.name, release.number, form.data)
            abort(400)

        db.session.add(release)
        db.session.commit()

        ops.evict()

        return redirect(url_for(
            'view_release',
            id=build.id,
            name=release.name,
            number=release.number))

    # Update form values for rendering
    form.good.data = True
    form.bad.data = True
    form.reviewing.data = True

    return render_template(
        'view_release.html',
        build=build,
        release=release,
        run_list=run_list,
        release_form=form,
        approval_log=approval_log,
        stats_dict=stats_dict)


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
def view_run():
    """Page for viewing before/after for a specific test run."""
    build = g.build
    if request.method == 'POST':
        form = forms.RunForm(request.form)
    else:
        form = forms.RunForm(request.args)

    form.validate()

    ops = operations.BuildOps(build.id)
    run, next_run, previous_run, approval_log = ops.get_run(
        form.name.data, form.number.data, form.test.data)

    if not run:
        abort(404)

    file_type = form.type.data
    image_file, log_file, config_file, sha1sum = (
        _get_artifact_context(run, file_type))

    if request.method == 'POST':
        if form.approve.data and run.status == models.Run.DIFF_FOUND:
            run.status = models.Run.DIFF_APPROVED
            auth.save_admin_log(build, run_approved=True, run=run)
        elif form.disapprove.data and run.status == models.Run.DIFF_APPROVED:
            run.status = models.Run.DIFF_FOUND
            auth.save_admin_log(build, run_rejected=True, run=run)
        else:
            abort(400)

        db.session.add(run)
        db.session.commit()

        ops.evict()

        return redirect(url_for(
            request.endpoint,
            id=build.id,
            name=run.release.name,
            number=run.release.number,
            test=run.name,
            type=file_type))

    # Update form values for rendering
    form.approve.data = True
    form.disapprove.data = True

    context = dict(
        build=build,
        release=run.release,
        run=run,
        run_form=form,
        previous_run=previous_run,
        next_run=next_run,
        file_type=file_type,
        image_file=image_file,
        log_file=log_file,
        config_file=config_file,
        sha1sum=sha1sum,
        approval_log=approval_log)

    if file_type:
        template_name = 'view_artifact.html'
    else:
        template_name = 'view_run.html'

    response = flask.Response(render_template(template_name, **context))

    return response


@app.route('/settings', methods=['GET', 'POST'])
@auth.build_access_required('build_id')
def build_settings():
    build = g.build

    settings_form = forms.SettingsForm()

    if settings_form.validate_on_submit():
        settings_form.populate_obj(build)

        message = ('name=%s, send_email=%s, email_alias=%s' % (
            build.name, build.send_email, build.email_alias))
        auth.save_admin_log(build, changed_settings=True, message=message)

        db.session.add(build)
        db.session.commit()

        signals.build_updated.send(app, build=build, user=current_user)

        return redirect(url_for(
            request.endpoint,
            build_id=build.id))

    # Update form values for rendering
    settings_form.name.data = build.name
    settings_form.build_id.data = build.id
    settings_form.email_alias.data = build.email_alias
    settings_form.send_email.data = build.send_email

    return render_template(
        'view_settings.html',
        build=build,
        settings_form=settings_form)
