#!/usr/bin/env python

"""TODO

# To use for the first time, or when the schema changes during development:
import sightdiff
sightdiff.db.create_all()

"""

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

import api
import work_queue
