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

"""Cacheable operations and eviction for models in the frontend.

By using an object and its methods for @cache.memoize, you tell Flask-Cache
to use a version number per object. That makes it easy to evict all
information related to a single build or a single user, while leaving all
other caches alone.
"""

# Local modules
from . import app
from . import cache
from . import db
from dpxdt.server import models
from dpxdt.server import signals


class UserOps(object):
    """Cacheable operations for user-specified information."""

    def __init__(self, user_id):
        self.user_id = user_id

    # For Flask-Cache keys
    def __repr__(self):
        return 'caching.UserOps(user_id=%r)' % self.user_id

    @cache.memoize()
    def load(self):
        user = models.User.query.get(self.user_id)
        db.session.expunge(user)
        return user

    @cache.memoize()
    def get_builds(self):
        if self.user_id:
            user = models.User.query.get(self.user_id)
            build_list = (
                user.builds
                .order_by(models.Build.created.desc())
                .limit(1000)
                .all())
        else:
            # Anonymous users see only public builds
            build_list = (
                models.Build.query
                .filter_by(public=True)
                .order_by(models.Build.created.desc())
                .limit(1000)
                .all())

        for build in build_list:
            db.session.expunge(build)

        return build_list

    @cache.memoize()
    def owns_build(self, build_id):
        build = models.Build.query.get(build_id)
        user_is_owner = False
        if build:
            user_is_owner = build.is_owned_by(self.user_id)
            db.session.expunge(build)

        return build, user_is_owner

    def evict(self):
        """Evict all caches related to this user."""
        cache.delete_memoized(self.get_builds)
        cache.delete_memoized(self.owns_build)


class BuildOps(object):
    """Cacheable operations for build-specific operations."""

    def __init__(self, build_id):
        self.build_id = build_id

    # For Flask-Cache keys
    def __repr__(self):
        return 'caching.BuildOps(build_id=%r)' % self.build_id

    @cache.memoize()
    def get_next_previous_runs(self, run):
        next_run = None
        previous_run = None

        # We sort the runs in the release by diffs first, then by name.
        # Simulate that behavior here with multiple queries.
        if run.status in models.Run.DIFF_NEEDED_STATES:
            previous_run = (
                models.Run.query
                .filter_by(release_id=run.release_id)
                .filter(models.Run.status.in_(models.Run.DIFF_NEEDED_STATES))
                .filter(models.Run.name < run.name)
                .order_by(models.Run.name.desc())
                .first())
            next_run = (
                models.Run.query
                .filter_by(release_id=run.release_id)
                .filter(models.Run.status.in_(models.Run.DIFF_NEEDED_STATES))
                .filter(models.Run.name > run.name)
                .order_by(models.Run.name)
                .first())

            if not next_run:
                next_run = (
                    models.Run.query
                    .filter_by(release_id=run.release_id)
                    .filter(
                        ~models.Run.status.in_(models.Run.DIFF_NEEDED_STATES))
                    .order_by(models.Run.name)
                    .first())
        else:
            previous_run = (
                models.Run.query
                .filter_by(release_id=run.release_id)
                .filter(~models.Run.status.in_(models.Run.DIFF_NEEDED_STATES))
                .filter(models.Run.name < run.name)
                .order_by(models.Run.name.desc())
                .first())
            next_run = (
                models.Run.query
                .filter_by(release_id=run.release_id)
                .filter(~models.Run.status.in_(models.Run.DIFF_NEEDED_STATES))
                .filter(models.Run.name > run.name)
                .order_by(models.Run.name)
                .first())

            if not previous_run:
                previous_run = (
                    models.Run.query
                    .filter_by(release_id=run.release_id)
                    .filter(
                        models.Run.status.in_(models.Run.DIFF_NEEDED_STATES))
                    .order_by(models.Run.name.desc())
                    .first())

        if next_run:
            db.session.expunge(next_run)
        if previous_run:
            db.session.expunge(previous_run)

        return next_run, previous_run

    def evict(self):
        """Evict all caches relating to this build."""
        cache.delete_memoized(self.get_next_previous_runs)


# Connect API events to cache eviction.

def _evict_run_cache(cls, build=None, release=None, run=None):
    BuildOps(build.id).evict()


signals.run_updated_via_api.connect(_evict_run_cache, app)
