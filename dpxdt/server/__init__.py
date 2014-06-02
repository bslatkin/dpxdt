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

"""Main module for the API server."""

import datetime
import logging
import os

# Local libraries
from flask import Flask, url_for
from flask.ext.cache import Cache
from flask.ext.login import LoginManager
from flask.ext.mail import Mail
from flask.ext.sqlalchemy import SQLAlchemy
import jinja2

# Local modules required for app setup
import config


app = Flask(__name__)
app.config.from_object(config)


db = SQLAlchemy(
    app,
    # Don't expire model instances on commit. Let functions continue to
    # quickly read properties from their last known-good state.
    session_options=dict(expire_on_commit=False))


login = LoginManager(app)
login.login_view = 'login_view'
login.refresh_view = 'login_view'


cache = Cache(app)


mail = Mail(app)


# Modules with handlers to register with the app
from dpxdt.server import api
from dpxdt.server import auth
from dpxdt.server import emails
from dpxdt.server import frontend
from dpxdt.server import work_queue
from dpxdt.server import work_queue_handlers
