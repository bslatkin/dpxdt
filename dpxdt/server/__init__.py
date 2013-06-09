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

"""Main module for the API server.

# To use for the first time, or when the schema changes during development:
from dpxdt.server import db
db.drop_all()
db.create_all()

# To deploy this to a CloudSQL database on App Engine. You will have to
# change your instance name based on settings in config.py.
./google_sql.sh dpxdt-project:test
sql> create database test;

"""

import config

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import LoginManager

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = config.SECRET_KEY

db = SQLAlchemy(app)

login = LoginManager()
login.init_app(app)
login.login_view = 'login_view'

import api
import auth
import frontend
import work_queue
