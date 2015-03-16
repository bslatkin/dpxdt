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

import logging

# Local libraries
import cloudstorage
import flask

# Local modules
from dpxdt.server import app
from dpxdt.server import config


# TODO: Merge these hooks into dpxdt/server/api.py so they can be used
# in any deployment context, not just App Engine.


def _artifact_created(artifact):
    """Override for saving an artifact to google storage."""
    filename = '/%s/sha1-%s' % (
        config.GOOGLE_CLOUD_STORAGE_BUCKET, artifact.id)

    with cloudstorage.open(
            filename, 'w', content_type=artifact.content_type) as handle:
        handle.write(artifact.data)

    artifact.data = None
    artifact.alternate = filename
    logging.debug('Saved artifact_id=%r, alternate=%r',
                  artifact.id, artifact.alternate)


def _get_artifact_response(artifact):
    """Override for serving an artifact from Google Cloud Storage."""
     if artifact.alternate:
        filename = artifact.alternate

        # Trim any old /gs prefixes that were there for the old files API.
        if filename.startswith('/gs'):
            filename = filename[len('/gs'):]

        # TODO: Issue a temporarily authorized redirect to cloud storage
        # instead of proxying the data here. This is fully proxying the
        # data so internal redirects within Flask will work correctly.
        with cloudstorage.open(filename, 'r') as handle:
            data = handle.read()
        logging.debug('Serving artifact_id=%r, alternate=%r',
                      artifact.id, filename)
    else:
        data = artifact.data

    response = flask.Response(data, mimetype=artifact.content_type)
    response.cache_control.public = True
    response.cache_control.max_age = 8640000
    response.set_etag(artifact.id)
    return response
