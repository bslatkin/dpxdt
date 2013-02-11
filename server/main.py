#!/usr/bin/env python

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


class Artifact(db.Model):
  """Contains a single file uploaded by a diff worker."""

  id = db.Column(db.String(40), primary_key=True)
  data = db.Column(db.LargeBinary)
  content_type = db.Column(db.String(50))

  # TODO: Add owner, build name, release name, candidate name
  # TODO: Add support for external data resource, like on S3


@app.route('/')
def hello_world():
  return 'Hello World!'


@app.route('/api/upload', methods=['POST'])
def upload():
  if len(request.files) != 1:
    return 'Need exactly one file', 400

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
