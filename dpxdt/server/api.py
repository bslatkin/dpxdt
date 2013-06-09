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

"""Web-based API for managing screenshots and incremental perceptual diffs.

Lifecycle of a release:

1. User creates a new build, which represents a single product or site that
   will be screenshotted repeatedly over time. This may happen very
   infrequenty through a web UI.

2. User creates a new release candidate for the build with a specific release
   name. The candidate is an attempt at finishing a specific release name. It
   may take many attempts, many candidates, before the release with that name
   is complete and can be marked as good.

3. User creates many runs for the candidate created in #2. Each run is
   identified by a unique name that describes what it does. For example, the
   run name could be the URL path for a page being screenshotted. The user
   associates each run with a new screenshot artifact. Runs are automatically
   associated with a corresponding run from the last good release. This makes
   it easy to compare new and old screenshots for runs with the same name.

4. User uploads a series of screenshot artifacts identified by content hash.
   Perceptual diffs between these new screenshots and the last good release
   may also be uploaded as an optimization. This may happen in parallel
   with #3.

5. The user marks the release candidate as having all of its expected runs
   present, meaning it will no longer receive new runs. This should only
   happen after all screenshot artifacts have finished uploading.

6. If a run indicates a previous screenshot, but no perceptual diff has
   been made to compare the new and old versions, a worker will do a perceptual
   diff, upload it, and associate it with the run.

7. Once all perceptual diffs for a release candidate's runs are complete,
   the results of the candidate are emailed out to the build's owner.

8. The build owner can go into a web UI, inspect the new/old perceptual diffs,
   and mark certain runs as okay even though the perceptual diff showed a
   difference. For example, a new feature will cause a perceptual diff, but
   should not be treated as a failure.

9. The user decides the release candidate looks correct and marks it as good,
   or the user thinks the candidate looks bad and goes back to #2 and begins
   creating a new candidate for that release all over again.


Notes:

- At any time, a user can manually mark any candidate or release as bad. This
  is useful to deal with bugs in the screenshotter, mistakes in approving a
  release candidate, rolling back to an earlier version, etc.

- As soon as a new release name is cut for a build, the last candidate of
  the last release is marked as good if there is no other good candidate. This
  lets the API establish a "baseline" release easily for first-time users.

- Only one release candidate may be receiving runs for a build at a time.
"""

import datetime
import hashlib
import functools
import json
import logging
import mimetypes

# Local libraries
import flask
from flask import Flask, abort, request
from flask.ext.login import current_user, login_required

# Local modules
from . import app
from . import db
import models
import work_queue
import utils


def api_key_required(f):
    """Decorator ensures API key has proper access to requested resources."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth:
            logging.debug('API request lacks authorization header')
            return flask.Response(
                'API key required', 401,
                {'WWW-Authenticate', 'Basic realm="API key required"'})

        api_key = models.ApiKey.query.get(auth.username)
        if not api_key:
            logging.debug('API key=%r does not exist', auth.username)
            return abort(403)

        if not api_key.active:
            logging.debug('API key=%r is no longer active', api_key.id)
            return abort(403)

        if api_key.secret != auth.password:
            logging.debug('API key=%r password does not match', api_key.id)
            return abort(403)

        logging.debug('Authenticated as API key=%r', api_key.id)

        build_id = request.form.get('build_id', type=int)

        if not api_key.superuser:
            if build_id and api_key.build_id == build_id:
                # Only allow normal users to edit builds that exist.
                build = models.Build.query.get(build_id)
                if not build:
                    logging.debug('API key=%r accessing missing build_id=%r',
                                  api_key.id, build_id)
                    return abort(404)
            else:
                logging.debug('API key=%r cannot access requested build_id=%r',
                              api_key.id, build_id)
                return abort(403)

        return f(*args, **kwargs)

    return wrapped


@app.route('/api/create_release', methods=['POST'])
@api_key_required
def create_release():
    """Creates a new release candidate for a build."""
    build_id = request.form.get('build_id', type=int)
    utils.jsonify_assert(build_id is not None, 'build_id required')
    release_name = request.form.get('release_name')
    utils.jsonify_assert(release_name, 'release_name required')

    release = models.Release(
        name=release_name,
        number=1,
        build_id=build_id)

    last_candidate = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name)
        .order_by(models.Release.number.desc())
        .first())
    if last_candidate:
        release.number += last_candidate.number

    db.session.add(release)
    db.session.commit()

    logging.info('Created release: build_id=%r, release_name=%r, '
                 'release_number=%d', build_id, release_name, release.number)

    return flask.jsonify(
        build_id=build_id,
        release_name=release_name,
        release_number=release.number)


def _check_release_done_processing(release_id):
    """Moves a release candidate to reviewing if all runs are done."""
    release = models.Release.query.get(release_id)
    if not release:
        logging.error('Could not find release_id=%r', release_id)
        return False

    if release.status != models.Release.PROCESSING:
        logging.debug('Not yet processing: release_id=%r', release_id)
        return False

    query = models.Run.query.filter_by(release_id=release.id)
    for run in query:
        if run.status == models.Run.NEEDS_DIFF:
            return False

    logging.info('Release done processing, now reviewing: build_id=%r, '
                 'name=%r, number=%d', release.build_id, release.name,
                 release.number)

    release.status = models.Release.REVIEWING
    db.session.add(release)
    return True


def _get_release_params():
    """Gets the release params from the current request."""
    build_id = request.form.get('build_id', type=int)
    utils.jsonify_assert(build_id is not None, 'build_id required')
    release_name = request.form.get('release_name')
    utils.jsonify_assert(release_name, 'release_name required')
    release_number = request.form.get('release_number', type=int)
    utils.jsonify_assert(release_number is not None, 'release_number required')
    return build_id, release_name, release_number


@app.route('/api/find_run', methods=['POST'])
@api_key_required
def find_run():
    """Finds the last good run of the given name for a release."""
    build_id = request.form.get('build_id', type=int)
    utils.jsonify_assert(build_id is not None, 'build_id required')
    run_name = request.form.get('run_name', type=str)
    utils.jsonify_assert(run_name, 'run_name required')

    last_good_release = (
        models.Release.query
        .filter_by(
            build_id=build_id,
            status=models.Release.GOOD)
        .order_by(models.Release.created.desc())
        .first())

    if last_good_release:
        logging.debug('Found last good release for: build_id=%r, '
                      'release_name=%r, release_number=%d',
                      build_id, last_good_release.name,
                      last_good_release.number)
        last_good_run = (
            models.Run.query
            .filter_by(release_id=last_good_release.id, name=run_name)
            .first())
        if last_good_run:
            logging.debug('Found last good run for: build_id=%r, '
                          'release_name=%r, release_number=%d, '
                          'run_name=%r',
                          build_id, last_good_release.name,
                          last_good_release.number, run_name)
            return flask.jsonify(
                build_id=build_id,
                release_name=last_good_release.name,
                release_number=last_good_release.number,
                run_name=run_name,
                image=last_good_run.image,
                log=last_good_run.log,
                config=last_good_run.config)

    return utils.jsonify_error('Run not found')


@app.route('/api/report_run', methods=['POST'])
@api_key_required
def report_run():
    """Reports data for a run for a release candidate."""
    build_id, release_name, release_number = _get_release_params()
    run_name = request.form.get('run_name', type=str)
    utils.jsonify_assert(run_name, 'run_name required')

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    utils.jsonify_assert(release, 'release does not exist')

    run = (
        models.Run.query
        .filter_by(release_id=release.id, name=run_name)
        .first())
    if not run:
        logging.info('Created run: build_id=%r, release_name=%r, '
                     'release_number=%d, run_name=%r',
                     build_id, release_name, release_number, run_name)
        run = models.Run(
            release_id=release.id,
            name=run_name,
            status=models.Run.DATA_PENDING)

    current_image = request.form.get('image', type=str)
    current_log = request.form.get('log', type=str)
    current_config = request.form.get('config', type=str)

    ref_image = request.form.get('ref_image', type=str)
    ref_log = request.form.get('ref_log', type=str)
    ref_config = request.form.get('ref_config', type=str)

    diff_image = request.form.get('diff_image', type=str)
    diff_log = request.form.get('diff_log', type=str)

    if current_image:
        run.image = current_image
    if current_log:
        run.log = current_log
    if current_config:
        run.config = current_config
    if current_image or current_log or current_config:
        logging.info('Saved run data: build_id=%r, release_name=%r, '
                     'release_number=%d, run_name=%r, '
                     'image=%r, log=%r, config=%r',
                     build_id, release_name, release_number, run_name,
                     run.image, run.log, run.config)

    if ref_image:
        run.ref_image = ref_image
    if ref_log:
        run.ref_log = ref_log
    if ref_config:
        run.ref_config = ref_config
    if ref_image or ref_log or ref_config:
        logging.info('Saved reference data: build_id=%r, release_name=%r, '
                     'release_number=%d, run_name=%r, '
                     'ref_image=%r, ref_log=%r, ref_config=%r',
                     build_id, release_name, release_number, run_name,
                     run.ref_image, run.ref_log, run.ref_config)

    if diff_image:
        run.diff_image = diff_image
    if diff_log:
        run.diff_log = diff_log
    if diff_image or diff_log:
        logging.info('Saved pdiff: build_id=%r, release_name=%r, '
                     'release_number=%d, run_name=%r, '
                     'diff_image=%r, diff_log=%r',
                     build_id, release_name, release_number, run_name,
                     run.diff_image, run.diff_log)

    if run.diff_image:
        run.status = models.Run.DIFF_FOUND
    elif run.ref_image and not run.diff_log:
        run.status = models.Run.NEEDS_DIFF
    elif run.ref_image and run.diff_log:
        run.status = models.Run.DIFF_NOT_FOUND
    elif request.form.get('no_diff_needed', type=str):
        run.status = models.Run.NO_DIFF_NEEDED

    if run.status == models.Run.NEEDS_DIFF:
        # TODO: Move this queue name to a flag.
        work_queue.add('run-pdiff', dict(
            build_id=build_id,
            release_name=release_name,
            release_number=release_number,
            run_name=run_name,
            run_sha1sum=current_image,
            reference_sha1sum=ref_image,
        ))

    # Flush the run so querying for Runs in _check_release_done_processing
    # will be find the new run too.
    db.session.add(run)
    db.session.flush()
    _check_release_done_processing(run.release_id)

    db.session.commit()

    logging.info('Updated run: build_id=%r, release_name=%r, '
                 'release_number=%d, run_name=%r, status=%r',
                 build_id, release_name, release_number, run_name, run.status)

    return flask.jsonify(success=True)


@app.route('/api/runs_done', methods=['POST'])
@api_key_required
def runs_done():
    """Marks a release candidate as having all runs reported."""
    build_id, release_name, release_number = _get_release_params()

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    utils.jsonify_assert(release, 'Release does not exist')

    release.status = models.Release.PROCESSING
    db.session.add(release)
    _check_release_done_processing(release.id)
    db.session.commit()

    logging.info('Runs done for release: build_id=%r, release_name=%r, '
                 'release_number=%d', build_id, release_name, release_number)

    return flask.jsonify(success=True)


@app.route('/api/release_done', methods=['POST'])
@api_key_required
def release_done():
    """Marks a release candidate as good or bad."""
    build_id, release_name, release_number = _get_release_params()
    status = request.form.get('status')
    valid_statuses = (models.Release.GOOD, models.Release.BAD)
    utils.jsonify_assert(status in valid_statuses,
                         'status must be in %r' % valid_statuses)

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    utils.jsonify_assert(release, 'Release does not exist')

    release.status = status
    db.session.add(release)
    db.session.commit()

    logging.info('Release marked as %s: build_id=%r, release_name=%r, '
                 'number=%d', status, build_id, release_name, release_number)

    return flask.jsonify(success=True)


@app.route('/api/upload', methods=['POST'])
@api_key_required
def upload():
    """Uploads an artifact referenced by a run."""
    utils.jsonify_assert(len(request.files) == 1,
                         'Need exactly one uploaded file')

    file_storage = request.files.values()[0]
    data = file_storage.read()
    sha1sum = hashlib.sha1(data).hexdigest()
    exists = models.Artifact.query.filter_by(id=sha1sum).first()
    if exists:
        logging.info('Upload already exists: artifact_id=%r', sha1sum)
        return flask.jsonify(sha1sum=sha1sum)

    # TODO: Mark that this owner/build has access to this sha1sum, to prevent
    # users from pointing at sha1sums of images they don't own? Maybe too
    # paranoid.

    content_type, _ = mimetypes.guess_type(file_storage.filename)
    artifact = models.Artifact(
        id=sha1sum,
        content_type=content_type,
        data=data)
    db.session.add(artifact)
    db.session.commit()

    logging.info('Upload received: artifact_id=%r, content_type=%r',
                 sha1sum, content_type)
    return flask.jsonify(sha1sum=sha1sum)


@app.route('/api/download')
@api_key_required
def download():
    """Downloads an artifact by it's content hash."""
    # TODO: Enforce build/release ownership of or access to the file
    sha1sum = request.args.get('sha1sum', type=str)
    artifact = models.Artifact.query.get(sha1sum)
    if not artifact:
        abort(404)

    if request.if_none_match and request.if_none_match.contains(sha1sum):
        return flask.Response(status=304)

    response = flask.Response(
        artifact.data,
        content_type=artifact.content_type)
    response.cache_control.private = True
    response.cache_control.max_age = 8640000
    response.set_etag(sha1sum)
    return response


@app.route('/api_keys', methods=['GET', 'POST'])
@login_required
def manage_api_keys():
    """Page for viewing and managing API keys."""
    user_is_owner = build.owners.filter_by(
                id=current_user.get_id()).first()

    form = forms.ApiKeyForm()
    if form.validate_on_submit():
        if form.id.data and form.revoke.data:


        build = models.Build()
        form.populate_obj(build)
        build.owners.append(current_user)
        db.session.add(build)
        db.session.commit()

        logging.info('Created build via UI: build_id=%r, name=%r',
                     build.id, build.name)
        return redirect(url_for('manage_api_keys', id=build.id))

    return render_template(
        'new_build.html',
        build_form=form)



    pass
