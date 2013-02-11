#!/usr/bin/env python

import datetime
import hashlib
import logging
import mimetypes

# Local libraries
import flask
from flask import Flask, request
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)


class Build(db.Model):
  """A single repository of artifacts and diffs owned by someone.

  Queries:
  - Get all builds for a specific owner.
  - Can this user read this build.
  - Can this user write this build.
  """

  id = db.Column(db.Integer, primary_key=True)
  creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
  name = db.Column(db.String(500))

  releases = db.relationship(
      'Release', backref=db.backref('build', lazy='dynamic'), lazy='dynamic')

  # TODO: Add owner


class Release(db.Model):
  """A set of runs that are part of a build, grouped by a user-supplied name.

  Queries:
  - For a build, find me the active release with this name.
  - Mark this release as abandoned.
  - Show me all active releases for this build by unique name in order
    of creation date descending.
  """

  id = db.Column(db.Integer, primary_key=True)
  creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
  name = db.Column(db.String(500))
  status = db.Column(db.Enum('live', 'dead'), default='live')

  build_id = db.Column(db.Integer, db.ForeignKey('build.id'))

  runs = db.relationship(
      'Run', backref=db.backref('release', lazy='dynamic'), lazy='dynamic')


class Artifact(db.Model):
  """Contains a single file uploaded by a diff worker."""

  id = db.Column(db.String(40), primary_key=True)
  creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
  data = db.Column(db.LargeBinary)
  content_type = db.Column(db.String(50))
  # TODO: Add support for external data resource, like on S3


class Run(db.Model):
  """Contains a set of screenshot records uploaded by a diff worker.

  Queries:
  - Show me all runs for the given release.
  - Show me all runs with the given name for all releases that are live.
  """

  id = db.Column(db.Integer, primary_key=True)
  creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
  name = db.Column(db.String(500))

  release_id = db.Column(db.Integer, db.ForeignKey('release.id'))

  current_image = db.Column(db.String, db.ForeignKey('artifact.id'))
  current_log = db.Column(db.String, db.ForeignKey('artifact.id'))
  current_config = db.Column(db.String, db.ForeignKey('artifact.id'))

  previous_image = db.Column(db.String, db.ForeignKey('artifact.id'))
  previous_log = db.Column(db.String, db.ForeignKey('artifact.id'))
  previous_config = db.Column(db.String, db.ForeignKey('artifact.id'))

  diff_image = db.Column(db.String, db.ForeignKey('artifact.id'))
  diff_log = db.Column(db.String, db.ForeignKey('artifact.id'))

  # TODO: Add indexes for all queries.
  # __table_args__ = (db.Index('vertial', 'release', 'candidate'),)


@app.route('/api/build', methods=['POST'])
def create_build():
  name = request.form.get('name')
  assert name, 'name required'

  # TODO: Make sure the requesting user is logged in

  build = Build(name=name)
  db.session.add(build)
  db.session.commit()

  logging.info('Created build: build_id=%s, name=%r', build.id, name)

  return flask.jsonify(build_id=build.id, name=name)


@app.route('/api/release', methods=['POST'])
def create_release():
  name = request.form.get('name')
  assert name, 'name required'
  build_id = request.form.get('build_id', type=int)
  assert build_id, 'build_id required'

  # TODO: Make sure build_id exists
  # TODO: Make sure requesting user is owner of the build_id

  last_release = Release.query.filter_by(
      build_id=build_id,
      name=name,
      status='live').first()
  if last_release:
    last_release.status = 'dead'
    logging.info('Marked release as dead: build_id=%s, name=%r, release_id=%s',
                 build_id, name, last_release.id)
    db.session.add(last_release)

  release = Release(
      name=name,
      build_id=build_id)
  db.session.add(release)
  db.session.commit()

  logging.info('Created release: build_id=%s, name=%r, release_id=%s',
               build_id, name, release.id)

  return flask.jsonify(release_id=release.id, build_id=build_id, name=name)


@app.route('/api/run', methods=['POST'])
def create_run():
  name = request.form.get('name')
  assert name, 'name required'
  release_id = request.form.get('release_id', type=int)
  assert release_id, 'release_id required'

  release = Release.query.filter_by(id=release_id).first()
  assert release, 'release_id does not exist'

  # TODO: Make sure requesting user is owner of the build_id

  current_image = request.form.get('current_image')
  current_log = request.form.get('current_log')
  current_config = request.form.get('current_config')

  previous_image = request.form.get('previous_image')
  previous_log = request.form.get('previous_log')
  previous_config = request.form.get('previous_config')

  diff_image = request.form.get('diff_image')
  diff_log = request.form.get('diff_log')

  # TODO: Make sure all referenced items exist? or don't and assume
  # the client is uploading them in parallel.

  fields = dict(
      name=name,
      release_id=release_id,
      current_image=current_image,
      current_log=current_log,
      current_config=current_config,
      previous_image=previous_image,
      previous_log=previous_log,
      previous_config=previous_config,
      diff_image=diff_image,
      diff_log=diff_log)

  run = Run(**fields)
  db.session.add(run)
  db.session.commit()

  logging.info('Created run: build_id=%s, name=%r, release_id=%s',
               release.build_id, name, release_id)

  return flask.jsonify(**fields)


@app.route('/api/upload', methods=['POST'])
def upload():
  assert len(request.files) != 1, 'Need exactly one uploaded file'

  # TODO: Require an API key on the basic auth header

  file_storage = request.files.values()[0]
  data = file_storage.read()
  sha1sum = hashlib.sha1(data).hexdigest()
  exists = Artifact.query.filter_by(id=sha1sum).first()
  if exists:
    logging.info('Upload already exists: artifact_id=%s', sha1sum)
    return flask.jsonify(sha1sum=sha1sum)

  # TODO: Depending on the environment, stash the data somewhere else.

  content_type, _ = mimetypes.guess_type(file_storage.filename)
  artifact = Artifact(
      id=sha1sum,
      content_type=content_type,
      data=data)
  db.session.add(artifact)
  db.session.commit()

  logging.info('Upload received: artifact_id=%s, content_type=%s',
               sha1sum, content_type)
  return flask.jsonify(sha1sum=sha1sum)


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.DEBUG)
  app.run(debug=True)
