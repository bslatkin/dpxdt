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
import json
import logging
import mimetypes

# Local libraries
import flask
from flask import Flask, request

# Local modules
from . import app
from . import db
import models
import work_queue
import utils


@app.route('/api/create_build', methods=['POST'])
def create_build():
    """Creates a new build for a user."""
    # TODO: Make sure the requesting user is logged in
    name = request.form.get('name')
    utils.jsonify_assert(name, 'name required')

    build = models.Build(name=name)
    db.session.add(build)
    db.session.commit()

    logging.info('Created build: build_id=%r, name=%r', build.id, name)

    return flask.jsonify(build_id=build.id, name=name)


@app.route('/api/create_release', methods=['POST'])
def create_release():
    """Creates a new release candidate for a build."""
    build_id = request.form.get('build_id', type=int)
    utils.jsonify_assert(build_id is not None, 'build_id required')
    release_name = request.form.get('release_name')
    utils.jsonify_assert(release_name, 'release_name required')
    # TODO: Make sure build_id exists
    # TODO: Make sure requesting user is owner of the build_id

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
        logging.error('Could not find release_id=%s', release_id)
        return False

    if release.status != models.Release.PROCESSING:
        logging.error('Already done processing: release_id=%s', release_id)
        return False

    query = models.Run.query.filter_by(release_id=release.id)
    for run in query:
        if run.needs_diff:
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


@app.route('/api/report_run', methods=['POST'])
def report_run():
    """Reports a new run for a release candidate."""
    build_id, release_name, release_number = _get_release_params()
    run_name = request.form.get('run_name', type=str)
    utils.jsonify_assert(run_name, 'run_name required')

    release = (
        models.Release.query
        .filter_by(build_id=build_id, name=release_name, number=release_number)
        .first())
    utils.jsonify_assert(release, 'release does not exist')
    # TODO: Make sure requesting user is owner of the build_id

    current_image = request.form.get('image', type=str)
    utils.jsonify_assert(current_image, 'image must be supplied')
    current_log = request.form.get('log', type=str)
    current_config = request.form.get('config', type=str)
    no_diff = request.form.get('no_diff')
    diff_image = request.form.get('diff_image', type=str)
    diff_log = request.form.get('diff_log', type=str)
    needs_diff = not (no_diff or diff_image or diff_log)

    # Find the previous corresponding run and automatically connect it.
    last_good_release = (
        models.Release.query
        .filter_by(
            build_id=build_id,
            status=models.Release.GOOD)
        .order_by(models.Release.created.desc())
        .first())
    previous_id = None
    last_image = None
    if last_good_release:
        logging.debug('Found last good release for: build_id=%r, '
                      'release_name=%r, release_number=%d, '
                      'last_good_release_id=%d',
                      build_id, release_name, release_number,
                      last_good_release.id)
        last_good_run = (
            models.Run.query
            .filter_by(release_id=last_good_release.id, name=run_name)
            .first())
        if last_good_run:
            logging.debug('Found last good run for: build_id=%r, '
                          'release_name=%r, release_number=%d, '
                          'last_good_release_id=%d, last_good_run_id=%r, '
                          'last_good_image=%r',
                          build_id, release_name, release_number,
                          last_good_release.id, last_good_run.id,
                          last_good_run.image)
            previous_id = last_good_run.id
            last_image = last_good_run.image

    run = models.Run(
        name=run_name,
        release_id=release.id,
        image=current_image,
        log=current_log,
        config=current_config,
        previous_id=previous_id,
        needs_diff=bool(needs_diff and last_image),
        diff_image=diff_image,
        diff_log=diff_log)
    db.session.add(run)
    db.session.flush()

    # Schedule pdiff if there isn't already an image.
    if needs_diff and last_image:
        # TODO: Move this queue name to a flag.
        work_queue.add('run-pdiff', dict(
            build_id=build_id,
            release_name=release_name,
            release_number=release_number,
            run_name=run_name,
            reference_sha1sum=current_image,
            run_sha1sum=last_image,
        ))

    db.session.commit()

    logging.info('Created run: build_id=%r, release_name=%r, '
                 'release_number=%d, run_name=%s',
                 build_id, release_name, release_number, run_name)

    return flask.jsonify(success=True)


@app.route('/api/report_pdiff', methods=['POST'])
def report_pdiff():
    """Reports a pdiff for a run.

    When there is no diff to report, supply the "no_diff" parameter.
    """
    build_id, release_name, release_number = _get_release_params()
    run_name = request.form.get('run_name', type=str)
    utils.jsonify_assert(run_name, 'run_name required')

    release = (
        models.Release.query
        .filter_by(
            build_id=build_id,
            name=release_name)
        .first())
    utils.jsonify_assert(release, 'Release does not exist')
    run = (
        models.Run.query
        .filter_by(release_id=release.id, name=run_name)
        .first())
    utils.jsonify_assert(release, 'Run does not exist')

    no_diff = request.form.get('no_diff')
    run.needs_diff = not (no_diff or run.diff_image or run.diff_log)
    run.diff_image = request.form.get('diff_image', type=str)
    run.diff_log = request.form.get('diff_log', type=str)

    db.session.add(run)

    logging.info('Saved pdiff: build_id=%r, release_name=%r, '
                 'release_number=%d, run_name=%s, '
                 'no_diff=%s, diff_image=%s, diff_log=%s',
                 build_id, release_name, release_number, run_name,
                 no_diff, run.diff_image, run.diff_log)

    _check_release_done_processing(run.release_id)
    db.session.commit()

    return flask.jsonify(success=True)


@app.route('/api/runs_done', methods=['POST'])
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
def upload():
    """Uploads an artifact referenced by a run."""
    # TODO: Require an API key on the basic auth header
    utils.jsonify_assert(len(request.files) == 1,
                         'Need exactly one uploaded file')

    file_storage = request.files.values()[0]
    data = file_storage.read()
    sha1sum = hashlib.sha1(data).hexdigest()
    exists = models.Artifact.query.filter_by(id=sha1sum).first()
    if exists:
        logging.info('Upload already exists: artifact_id=%s', sha1sum)
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

    logging.info('Upload received: artifact_id=%s, content_type=%s',
                 sha1sum, content_type)
    return flask.jsonify(sha1sum=sha1sum)


@app.route('/api/download')
def download():
    """Downloads an artifact by it's content hash."""
    # TODO: Require an API key on the basic auth header
    # TODO: Enforce build/release ownership of or access to the file
    sha1sum = request.args.get('sha1sum')
    artifact = models.Artifact.query.get(sha1sum)
    if not artifact:
        abort(404)
    return flask.Response(artifact.data, content_type=artifact.content_type)
