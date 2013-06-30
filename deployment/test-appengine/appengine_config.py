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

import sys
sys.path.insert(0, './lib/')

# Local modules
from dpxdt.server import api
from dpxdt.server import app
import hooks


# For debugging SQL queries.
# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


# For RPC performance optimization.
# def webapp_add_wsgi_middleware(app):
#     from google.appengine.ext.appstats import recording
#     app = recording.appstats_wsgi_middleware(app)
#     return app


@app.route('/_ah/warmup')
def appengine_warmup():
    return 'OK'


# Install override hooks.
api._artifact_created = hooks._artifact_created
api._get_artifact_response = hooks._get_artifact_response
