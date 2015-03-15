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

"""Hook overrides for the App Engine environment."""

import datetime
import os
import logging

from google.appengine.api import files
from google.appengine.ext import blobstore

# Local libraries
import flask

# Local modules
from dpxdt.server import app
from dpxdt.server import models


GOOGLE_CLOUD_STORAGE_BUCKET = os.environ.get('GOOGLE_CLOUD_STORAGE_BUCKET')


def _artifact_created(artifact):
    """Override for saving an artifact to google storage."""
    filename = '/gs/%s/sha1-%s' % (GOOGLE_CLOUD_STORAGE_BUCKET, artifact.id)

    # TODO: Move to the new cloudstorage module once it works with
    # dev_appserver and the BLOB_KEY_HEADER.
    writable_filename = files.gs.create(
        filename, mime_type=artifact.content_type)

    with files.open(writable_filename, 'a') as handle:
        handle.write(artifact.data)

    files.finalize(writable_filename)

    artifact.data = None
    artifact.alternate = filename
    logging.debug('Saved file=%r', artifact.alternate)


def _get_artifact_response(artifact):
    """Override for serving an artifact from Google Cloud Storage."""
    if artifact.alternate:
        blob_key = blobstore.create_gs_key(artifact.alternate)
        logging.debug('Serving file=%r, key=%r', artifact.alternate, blob_key)
        response = flask.Response(
            headers={blobstore.BLOB_KEY_HEADER: str(blob_key)},
            mimetype=artifact.content_type)
    else:
        response = flask.Response(
            artifact.data,
            mimetype=artifact.content_type)

    response.cache_control.public = True
    response.cache_control.max_age = 8640000
    response.set_etag(artifact.id)
    return response
