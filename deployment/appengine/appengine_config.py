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

"""App Engine configuration file.

See:
    https://developers.google.com/appengine/docs/python/tools/appengineconfig
"""

import os
import logging
import sys


# Log to disk for managed VMs:
# https://cloud.google.com/appengine/docs/managed-vms/custom-runtimes#logging
if os.environ.get('LOG_TO_DISK'):
    logging.basicConfig(
        format='%(levelname)s %(filename)s:%(lineno)s] %(message)s',
        file='/var/log/app_engine/custom_logs/applogs.log',
        level=logging.DEBUG)


# Load up our app and all its dependencies. Make the environment sane.
sys.path.insert(0, './lib/')
from dpxdt.server import app


# TODO: Initialize flags from flags file or enviornment.


# When in production use precompiled templates. Sometimes templates break
# in production. To debug templates there, comment this out entirely.
if os.environ.get('SERVER_SOFTWARE', '').startswith('Google App Engine'):
    import jinja2
    app.jinja_env.auto_reload = False
    app.jinja_env.loader = jinja2.ModuleLoader('templates_compiled.zip')


# Install dpxdt.server override hooks.
from dpxdt.server import api
import hooks

api._artifact_created = hooks._artifact_created
api._get_artifact_response = hooks._get_artifact_response


# Don't log when appstats is active.
appstats_DUMP_LEVEL = -1

# SQLAlchemy stacks are really deep.
appstats_MAX_STACK = 20

# Use very shallow local variable reprs to reduce noise.
appstats_MAX_DEPTH = 2


# These are only used if gae_mini_profiler was properly installed
def gae_mini_profiler_should_profile_production():
    from google.appengine.api import users
    return users.is_current_user_admin()


def gae_mini_profiler_should_profile_development():
    return True


# Fix the appstats module's formatting helper function.
import appstats_monkey_patch
