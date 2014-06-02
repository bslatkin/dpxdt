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
    """

    EMAIL_INVITATION = 'email_invitation'
    GOOGLE_OAUTH2 = 'google_oauth2'
    AUTH_TYPES = frozenset([EMAIL_INVITATION, GOOGLE_OAUTH2])

    id = db.Column(db.String(255), primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    email_address = db.Column(db.String(255))
    superuser = db.Column(db.Boolean, default=False)

    def get_auth_type(self):
        return self.id.split(':', 1)[0]

    # For flask-cache memoize key.
    def __repr__(self):
        return 'User(id=%r)' % self.get_id()

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


class ApiKey(db.Model):
    """API access for an automated system."""

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


ownership_table = db.Table(
    'build_ownership',
    db.Column('build_id', db.Integer, db.ForeignKey('build.id')),
    db.Column('user_id', db.String(255), db.ForeignKey('user.id')))


class Build(db.Model):
    """A single repository of artifacts and diffs owned by someone."""

    id = db.Column(db.Integer, primary_key=True)
    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    modified = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)
    name = db.Column(db.String(255))
    public = db.Column(db.Boolean, default=False)
    owners = db.relationship('User', secondary=ownership_table,
                             backref=db.backref('builds', lazy='dynamic'),
                             lazy='dynamic')
    send_email = db.Column(db.Boolean, default=True)
    email_alias = db.Column(db.String(255))

    def is_owned_by(self, user_id):
        return self.owners.filter_by(id=user_id).first() is not None

    # For flask-cache memoize key.
    def __repr__(self):
        return 'Build(id=%r)' % self.id


class Release(db.Model):
    """A set of runs in a build, grouped by user-supplied name."""

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

    # For flask-cache memoize key.
    def __repr__(self):
        return 'Release(id=%r)' % self.id


artifact_ownership_table = db.Table(
    'artifact_ownership',
    db.Column('artifact', db.String(100), db.ForeignKey('artifact.id')),
    db.Column('build_id', db.Integer, db.ForeignKey('build.id')))


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
    """Contains a set of screenshot records uploaded by a diff worker."""

    DATA_PENDING = 'data_pending'
    DIFF_APPROVED = 'diff_approved'
    DIFF_FOUND = 'diff_found'
    DIFF_NOT_FOUND = 'diff_not_found'
    FAILED = 'failed'
    NEEDS_DIFF = 'needs_diff'
    NO_DIFF_NEEDED = 'no_diff_needed'

    STATES = frozenset([
        DATA_PENDING, DIFF_APPROVED, DIFF_FOUND, DIFF_NOT_FOUND,
        FAILED, NEEDS_DIFF, NO_DIFF_NEEDED])

    DIFF_NEEDED_STATES = frozenset([DIFF_FOUND, DIFF_APPROVED])

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('release.id'))
    release = db.relationship('Release',
                              backref=db.backref('runs', lazy='select'),
                              lazy='joined',
                              join_depth=1)

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
    distortion = db.Column(db.Float())

    tasks = db.relationship('WorkQueue',
                            backref=db.backref('runs', lazy='select'),
                            lazy='joined',
                            join_depth=1,
                            order_by='WorkQueue.created')

    # For flask-cache memoize key.
    def __repr__(self):
        return 'Run(id=%r)' % self.id


class AdminLog(db.Model):
    """Log of admin user actions for a build."""

    CHANGED_SETTINGS = 'changed_settings'
    CREATED_API_KEY = 'created_api_key'
    CREATED_BUILD = 'created_build'
    INVITE_ACCEPTED = 'invite_accepted'
    INVITED_NEW_ADMIN = 'invited_new_admin'
    REVOKED_ADMIN = 'revoked_admin'
    REVOKED_API_KEY = 'revoked_api_key'
    RUN_APPROVED = 'run_approved'
    RUN_REJECTED = 'run_rejected'
    RELEASE_BAD = 'release_bad'
    RELEASE_GOOD = 'release_good'
    RELEASE_REVIEWING = 'release_reviewing'

    LOG_TYPES = frozenset([
        CHANGED_SETTINGS, CREATED_API_KEY, CREATED_BUILD, INVITE_ACCEPTED,
        INVITED_NEW_ADMIN, REVOKED_ADMIN, REVOKED_API_KEY, RUN_APPROVED,
        RUN_REJECTED, RELEASE_BAD, RELEASE_GOOD, RELEASE_REVIEWING])

    id = db.Column(db.Integer, primary_key=True)
    build_id = db.Column(db.Integer, db.ForeignKey('build.id'), nullable=False)

    release_id = db.Column(db.Integer, db.ForeignKey('release.id'))
    release = db.relationship('Release', lazy='joined', join_depth=2)

    run_id = db.Column(db.Integer, db.ForeignKey('run.id'))
    run = db.relationship('Run', lazy='joined', join_depth=1)

    user_id = db.Column(db.String(255), db.ForeignKey('user.id'))
    user = db.relationship('User', lazy='joined', join_depth=1)

    created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    log_type = db.Column(db.Enum(*LOG_TYPES), nullable=False)
    message = db.Column(db.Text)

    # For flask-cache memoize key.
    def __repr__(self):
        return 'AdminLog(id=%r)' % self.id
