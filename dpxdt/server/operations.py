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
from dpxdt.server import utils
from dpxdt.server import work_queue


class UserOps(object):
    """Cacheable operations for user-specific information."""

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


class ApiKeyOps(object):
    """Cacheable operations for API key-specific information."""

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    # For Flask-Cache keys
    def __repr__(self):
        return 'caching.ApiKeyOps(client_id=%r)' % self.client_id

    @cache.memoize(per_instance=True)
    def get(self):
        api_key = models.ApiKey.query.get(self.client_id)
        utils.jsonify_assert(api_key, 'API key must exist', 403)
        utils.jsonify_assert(api_key.active, 'API key must be active', 403)
        utils.jsonify_assert(api_key.secret == self.client_secret,
                             'Must have good credentials', 403)
        return api_key

    @cache.memoize(per_instance=True)
    def can_access_build(self, build_id):
        api_key = self.get()

        build = models.Build.query.get(build_id)
        utils.jsonify_assert(build is not None, 'build must exist', 404)

        if not api_key.superuser:
            utils.jsonify_assert(api_key.build_id == build_id,
                                 'API key must have access', 404)

        return api_key, build

    def evict(self):
        """Evict all caches related to this API key."""
        logging.debug('Evicting cache for %r', self)
        cache.delete_memoized(self.get)
        cache.delete_memoized(self.can_access_build)


class BuildOps(object):
    """Cacheable operations for build-specific operations."""

    def __init__(self, build_id):
        self.build_id = build_id

    # For Flask-Cache keys
    def __repr__(self):
        return 'caching.BuildOps(build_id=%r)' % self.build_id

    @staticmethod
    def sort_run(run):
        """Sort function for runs within a release."""
        # Sort errors first, then by name. Also show errors that were manually
        # approved, so the paging sort order stays the same even after users
        # approve a diff on the run page.
        if run.status in models.Run.DIFF_NEEDED_STATES:
            return (0, run.name)
        return (1, run.name)

    @staticmethod
    def get_stats_keys(status):
        if status in (models.Run.DIFF_APPROVED,
                      models.Run.DIFF_NOT_FOUND):
            return ('runs_successful', 'runs_complete', 'runs_total')
        elif status in models.Run.DIFF_FOUND:
            return ('runs_failed', 'runs_complete', 'runs_total')
        elif status == models.Run.NO_DIFF_NEEDED:
            return ('runs_baseline',)
        elif status == models.Run.NEEDS_DIFF:
            return ('runs_total', 'runs_pending')
        elif status == models.Run.FAILED:
            return ('runs_failed',)
        return ('runs_pending',)

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

        has_next_page = len(candidate_list) > page_size
        if has_next_page:
            candidate_list = candidate_list[:-1]

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

        return has_next_page, candidate_list, stats_counts

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
            return None, None, None, None

        run_list = list(release.runs)
        run_list.sort(key=BuildOps.sort_run)

        stats_dict = dict(
            runs_total=0,
            runs_complete=0,
            runs_successful=0,
            runs_failed=0,
            runs_baseline=0,
            runs_pending=0)
        for run in run_list:
            for key in self.get_stats_keys(run.status):
                stats_dict[key] += 1

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

        return release, run_list, stats_dict, approval_log

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



# Connect Frontend and API events to cache eviction.


def _evict_user_cache(sender, user=None, build=None):
    UserOps(user.get_id()).evict()


def _evict_build_cache(sender, build=None, release=None, run=None):
    BuildOps(build.id).evict()


def _evict_task_cache(sender, task=None):
    if not task.run_id:
        return
    run = models.Run.query.get(task.run_id)
    # Update the modification time on the run, since the task status changed.
    db.session.add(run)
    BuildOps(run.release.build_id).evict()


signals.build_updated.connect(_evict_user_cache, app)
signals.release_updated_via_api.connect(_evict_build_cache, app)
signals.run_updated_via_api.connect(_evict_build_cache, app)
signals.task_updated.connect(_evict_task_cache, app)
