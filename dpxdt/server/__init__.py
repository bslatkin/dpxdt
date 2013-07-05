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
from flask.ext.cache import Cache
from flask.ext.login import LoginManager
from flask.ext.sqlalchemy import SQLAlchemy
import jinja2

# Local modules required for app setup
import config


app = Flask(__name__)
app.config['CACHE_TYPE'] = config.CACHE_TYPE
app.config['CACHE_DEFAULT_TIMEOUT'] = config.CACHE_DEFAULT_TIMEOUT
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['REMEMBER_COOKIE_DOMAIN'] = config.REMEMBER_COOKIE_DOMAIN
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI


db = SQLAlchemy(app)


login = LoginManager()
login.init_app(app)
login.login_view = 'login_view'
login.refresh_view = 'login_view'


cache = Cache()
cache.init_app(app)


app.jinja_env.bytecode_cache = jinja2.MemcachedBytecodeCache(cache)


# Modules with handlers to register with the app
import api
import auth
import frontend
import work_queue
