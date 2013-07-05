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

# Load up our app and all its dependencies. Make the environment sane.
import sys
sys.path.insert(0, './lib/')
from dpxdt.server import app


# For debugging SQL queries.
# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


# For RPC performance optimization.
# def webapp_add_wsgi_middleware(app):
#     from google.appengine.ext.appstats import recording
#     app = recording.appstats_wsgi_middleware(app)
#     return app


def gae_mini_profiler_should_profile_production():
    from google.appengine.api import users
    return users.is_current_user_admin()


def gae_mini_profiler_should_profile_development():
    return True
