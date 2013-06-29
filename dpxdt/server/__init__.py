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

# Local libraries
from flask import Flask, url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager

# Local modules required for app setup
import config


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['REMEMBER_COOKIE_NAME'] = 'dpxdt_uid'
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=1)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI


db = SQLAlchemy(app)


login = LoginManager()
login.init_app(app)
login.login_view = 'login_view'
login.refresh_view = 'login_view'


# Modules with handlers to register with the app
import api
import auth
import frontend
import work_queue
