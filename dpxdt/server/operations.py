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

"""Cacheable operations and eviction for models in the frontend."""

import functools
import logging

# Local libraries
import sqlalchemy

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

    @cache.memoize(per_instance=True)
    def load(self):
        if not self.user_id:
            return None
        user = models.User.query.get(self.user_id)
        if user:
            db.session.expunge(user)
        return user

    @cache.memoize(per_instance=True)
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

    @cache.memoize(per_instance=True)
    def owns_build(self, build_id):
        build = models.Build.query.get(build_id)
        user_is_owner = False
        if build:
            user_is_owner = build.is_owned_by(self.user_id)
            db.session.expunge(build)

        return build, user_is_owner

    def evict(self):
        """Evict all caches related to this user."""
        logging.debug('Evicting cache for %r', self)
        cache.delete_memoized(self.load)
        cache.delete_memoized(self.get_builds)
        cache.delete_memoized(self.owns_build)


class BuildOps(object):
    """Cacheable operations for build-specific operations."""

    def __init__(self, build_id):
        self.build_id = build_id

    # For Flask-Cache keys
    def __repr__(self):
        return 'caching.BuildOps(build_id=%r)' % self.build_id

    @cache.memoize(per_instance=True)
    def get_candidates(self, page_size, offset):
        candidate_list = (
            models.Release.query
            .filter_by(build_id=self.build_id)
            .order_by(models.Release.created.desc())
            .offset(offset)
            .limit(page_size + 1)
            .all())

        stats_counts = []

        if candidate_list:
            candidate_keys = [c.id for c in candidate_list]
            stats_counts = (
                db.session.query(
                    models.Run.release_id,
                    models.Run.status,
                    sqlalchemy.func.count(models.Run.id))
                .join(models.Release)
                .filter(models.Release.id.in_(candidate_keys))
                .group_by(models.Run.status, models.Run.release_id)
                .all())

        for candidate in candidate_list:
            db.session.expunge(candidate)

        return candidate_list, stats_counts

    @cache.memoize(per_instance=True)
    def get_release(self, release_name, release_number):
        release = (
            models.Release.query
            .filter_by(
                build_id=self.build_id,
                name=release_name,
                number=release_number)
            .first())

        if not release:
            return None, None, None

        run_list = list(release.runs)

        approval_log = None
        if release.status in (models.Release.GOOD, models.Release.BAD):
            approval_log = (
                models.AdminLog.query
                .filter_by(release_id=release.id)
                .filter(models.AdminLog.log_type.in_(
                    (models.AdminLog.RELEASE_BAD,
                     models.AdminLog.RELEASE_GOOD)))
                .order_by(models.AdminLog.created.desc())
                .first())

        for run in run_list:
            db.session.expunge(run)

        if approval_log:
            db.session.expunge(approval_log)

        return release, run_list, approval_log

    def _get_next_previous_runs(self, run):
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

        return next_run, previous_run

    @cache.memoize(per_instance=True)
    def get_run(self, release_name, release_number, test_name):
        run = (
            models.Run.query
            .join(models.Release)
            .filter(models.Release.name == release_name)
            .filter(models.Release.number == release_number)
            .filter(models.Run.name == test_name)
            .first())
        if not run:
            return None, None, None, None

        next_run, previous_run = self._get_next_previous_runs(run)

        approval_log = None
        if run.status == models.Run.DIFF_APPROVED:
            approval_log = (
                models.AdminLog.query
                .filter_by(run_id=run.id,
                           log_type=models.AdminLog.RUN_APPROVED)
                .order_by(models.AdminLog.created.desc())
                .first())

        if run:
            db.session.expunge(run)
        if next_run:
            db.session.expunge(next_run)
        if previous_run:
            db.session.expunge(previous_run)
        if approval_log:
            db.session.expunge(approval_log)

        return run, next_run, previous_run, approval_log

    def evict(self):
        """Evict all caches relating to this build."""
        logging.debug('Evicting cache for %r', self)
        cache.delete_memoized(self.get_candidates)
        cache.delete_memoized(self.get_release)
        cache.delete_memoized(self.get_run)



# Connect API events to cache eviction.


def _evict_build_cache(sender, build=None, release=None, run=None):
    BuildOps(build.id).evict()


signals.release_updated_via_api.connect(_evict_build_cache, app)
signals.run_updated_via_api.connect(_evict_build_cache, app)
