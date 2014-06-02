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

"""Signals for frontend and API server requests."""


# Local modules
from blinker import Namespace


_signals = Namespace()


# The build settings have been modified. Sender is the app. Arguments
# are (models.Build, models.User). Signal is sent immediately *after* the
# Build is committed to the DB.
build_updated = _signals.signal('build-updated')


# A release has been created or updated via the API. Sender is the app.
# Arguments are (models.Build, models.Release). Signal is sent immediately
# *after* the Release is committed to the DB.
release_updated_via_api = _signals.signal('release-update')


# A run has been created or updated via the API. Sender is the app. Arguments
# are (models.Build, models.Release, models.Run). Signal is sent immediately
# *after* the Run is committed to the DB.
run_updated_via_api = _signals.signal('run-updated')

# A WorkQueue task's status has been updated via the API. Sender is the app.
# Argument is (work_queue.WorkQueue). Signal is sent immediately after the
# task is updated but before it is committed to the DB.
task_updated = _signals.signal('task-updated')
