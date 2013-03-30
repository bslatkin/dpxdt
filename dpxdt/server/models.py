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

"""Models for managing screenshots and incremental perceptual diffs."""

import datetime

# Local modules
from . import app
from . import db


class Build(db.Model):
    """A single repository of artifacts and diffs owned by someone.

    Queries:
    - Get all builds for a specific owner.
    - Can this user read this build.
    - Can this user write this build.
    """

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    name = db.Column(db.String)
    # TODO: Add owner


class Release(db.Model):
    """A set of runs that are part of a build, grouped by a user-supplied name.

    Queries:
    - For a build, find me the active release with this name.
    - Mark this release as abandoned.
    - Show me all active releases for this build by unique name in order
      of creation date descending.
    """

    RECEIVING = 'receiving'
    PROCESSING = 'processing'
    REVIEWING = 'reviewing'
    BAD = 'bad'
    GOOD = 'good'
    STATES = frozenset([RECEIVING, PROCESSING, REVIEWING, BAD, GOOD])

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    number = db.Column(db.Integer, nullable=False)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    status = db.Column(db.Enum(*STATES), default=RECEIVING, nullable=False)
    build_id = db.Column(db.Integer, db.ForeignKey('build.id'), nullable=False)


class Artifact(db.Model):
    """Contains a single file uploaded by a diff worker."""

    id = db.Column(db.String(40), primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    data = db.Column(db.LargeBinary)
    content_type = db.Column(db.String)
    # TODO: Actually save the blob files somewhere else, like S3. Add a
    # queue worker that uploads them there and purges the database. Move to
    # saving blobs in a directory by content-addressable filename.


class Run(db.Model):
    """Contains a set of screenshot records uploaded by a diff worker.

    Queries:
    - Show me all runs for the given release.
    - Show me all runs with the given name for all releases that are live.
    """

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'))
    name = db.Column(db.String, nullable=False)

    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    image = db.Column(db.String, db.ForeignKey('artifact.id'))
    log = db.Column(db.String, db.ForeignKey('artifact.id'))
    config = db.Column(db.String, db.ForeignKey('artifact.id'))

    previous_id = db.Column(db.Integer, db.ForeignKey('run.id'))

    needs_diff = db.Column(db.Boolean)
    diff_image = db.Column(db.String, db.ForeignKey('artifact.id'))
    diff_log = db.Column(db.String, db.ForeignKey('artifact.id'))
