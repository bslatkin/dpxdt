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


class User(db.Model):
    """Represents a user who is authenticated in the system.

    Primary key is prefixed with a valid AUTH_TYPES like:

        'google_oauth2:1234567890'

    To manually set a User to have superuser status:

        update user set superuser = 1 where user.id = '<user id here>';
    """

    GOOGLE_OAUTH2 = 'google_oauth2'
    AUTH_TYPES = frozenset([GOOGLE_OAUTH2])

    id = db.Column(db.String(255), primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    email_address = db.Column(db.String(255))
    superuser = db.Column(db.Boolean, default=False)

    # Methods required by flask-login.
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    def __eq__(self, other):
        return other.id == self.id

    def __ne__(self, other):
        return other.id != self.id


api_key_ownership_table = db.Table(
    'api_key_ownership',
    db.Column('api_key', db.String(255), db.ForeignKey('api_key.id')),
    db.Column('user_id', db.String(255), db.ForeignKey('user.id')))


class ApiKey(db.Model):
    """API access for an automated system.

    May be owned by multiple users if necessary. Owners can set its state
    to active or revoked. May be associated with a build, in which case all
    owners of the build may also control this API key. When set to superuser
    requestors using this API key will be able to operate on all builds.
    """

    id = db.Column(db.String(255), primary_key=True)
    secret = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True)
    purpose = db.Column(db.String(255))
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    modified = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)
    revoked = db.Column(db.DateTime)
    superuser = db.Column(db.Boolean, default=False)
    build_id = db.Column(db.Integer, db.ForeignKey('build.id'))
    owners = db.relationship('User', secondary=api_key_ownership_table,
                             backref=db.backref('api_keys', lazy='dynamic'),
                             lazy='dynamic')


ownership_table = db.Table(
    'build_ownership',
    db.Column('build_id', db.Integer, db.ForeignKey('build.id')),
    db.Column('user_id', db.String(255), db.ForeignKey('user.id')))


class Build(db.Model):
    """A single repository of artifacts and diffs owned by someone.

    Queries:
    - Get all builds for a specific owner.
    - Can this user read this build.
    - Can this user write this build.
    """

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    modified = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)
    name = db.Column(db.String(255))
    public = db.Column(db.Boolean, default=False)
    owners = db.relationship('User', secondary=ownership_table,
                             backref=db.backref('builds', lazy='dynamic'),
                             lazy='dynamic')


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
    name = db.Column(db.String(255), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    modified = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)
    status = db.Column(db.Enum(*STATES), default=RECEIVING, nullable=False)
    build_id = db.Column(db.Integer, db.ForeignKey('build.id'), nullable=False)
    url = db.Column(db.String(2048))


artifact_ownership_table = db.Table(
    'artifact_ownership',
    db.Column('artifact', db.String(100), db.ForeignKey('artifact.id')),
    db.Column('build_id', db.Integer, db.ForeignKey('build.id')))

# TODO: Actually save the blob files somewhere else, like S3. Add a
# queue worker that uploads them there and purges the database. Move to
# saving blobs in a directory by content-addressable filename.

class Artifact(db.Model):
    """Contains a single file uploaded by a diff worker."""

    id = db.Column(db.String(100), primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    data = db.Column(db.LargeBinary(length=2**31))
    alternate = db.Column(db.Text)
    content_type = db.Column(db.String(255))
    owners = db.relationship('Build', secondary=artifact_ownership_table,
                             backref=db.backref('artifacts', lazy='dynamic'),
                             lazy='dynamic')


class Run(db.Model):
    """Contains a set of screenshot records uploaded by a diff worker.

    Queries:
    - Show me all runs for the given release.
    - Show me all runs with the given name for all releases that are live.
    """

    DATA_PENDING = 'data_pending'
    DIFF_APPROVED = 'diff_approved'
    DIFF_FOUND = 'diff_found'
    DIFF_NOT_FOUND = 'diff_not_found'
    NEEDS_DIFF = 'needs_diff'
    NO_DIFF_NEEDED = 'no_diff_needed'
    STATES = frozenset([
        DATA_PENDING, DIFF_APPROVED, DIFF_FOUND, DIFF_NOT_FOUND,
        NEEDS_DIFF, NO_DIFF_NEEDED])

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'))
    name = db.Column(db.String(255), nullable=False)
    # TODO: Put rigid DB constraint on uniqueness of (release_id, name)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    modified = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)
    status = db.Column(db.Enum(*STATES), nullable=False)

    image = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    log = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    config = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    url = db.Column(db.String(2048))

    ref_image = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    ref_log = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    ref_config = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    ref_url = db.Column(db.String(2048))

    diff_image = db.Column(db.String(100), db.ForeignKey('artifact.id'))
    diff_log = db.Column(db.String(100), db.ForeignKey('artifact.id'))
