#!/usr/bin/env python

import datetime
import hashlib
import logging
import mimetypes

# Local libraries
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


@app.route('/api/upload', methods=['POST'])
def upload():
  if len(request.files) != 1:
    return 'Need exactly one file', 400

  # TODO: Require an API key on the basic auth header

  file_storage = request.files.values()[0]
  data = file_storage.read()
  sha1sum = hashlib.sha1(data).hexdigest()
  exists = Artifact.query.filter_by(id=sha1sum).first()
  if exists:
    logging.info('Upload already exists artifact=%s', sha1sum)
    return '', 200

  content_type, _ = mimetypes.guess_type(file_storage.filename)
  artifact = Artifact(
      id=sha1sum,
      content_type=content_type,
      data=data)
  db.session.add(artifact)
  db.session.commit()

  logging.info('Saved uploaded artifact=%s, content_type=%s',
               sha1sum, content_type)
  return '', 200


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.DEBUG)
  app.run(debug=True)
