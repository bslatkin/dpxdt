#!/usr/bin/env python

import sqlite3
import flask


app = flask.Flask(__name__)


DATABASE = '/tmp/database.db'


def connect_db():
  return sqlite3.connect(DATABASE)


@app.before_request
def before_request():
  flask.g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
  if hasattr(flask.g, 'db'):
    flask.g.db.close()


@app.route('/')
def hello_world():
  return 'Hello World!'


if __name__ == '__main__':
  app.run()
