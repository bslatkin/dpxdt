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

"""Implements authentication for the API server and frontend."""

import functools
import json
import logging
import urllib
import urllib2

# Local libraries
from flask import abort, redirect, render_template, request
from flask.ext.login import current_user, login_required, login_user

# Local modules
from . import app
from . import db
from . import login

import config
import models


GOOGLE_OAUTH2_AUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_OAUTH2_TOKEN_URL = 'https://accounts.google.com/o/oauth2/token'
GOOGLE_OAUTH2_USERINFO_URL = 'https://www.googleapis.com/oauth2/v1/userinfo'
GOOGLE_OAUTH2_SCOPES ='https://www.googleapis.com/auth/userinfo.email'
FETCH_TIMEOUT_SECONDS = 60


@login.user_loader
def load_user(user_id):
    return models.User.query.get(user_id)


@app.route('/login')
def login_view():
    # Inspired by:
    #   http://stackoverflow.com/questions/9499286
    #   /using-google-oauth2-with-flask
    params = dict(
        response_type='code',
        client_id=config.GOOGLE_OAUTH2_CLIENT_ID,
        redirect_uri=config.GOOGLE_OAUTH2_REDIRECT_URI,
        scope=GOOGLE_OAUTH2_SCOPES,
        state=request.args.get('next'),
    )
    target_url = '%s?%s' % (
        GOOGLE_OAUTH2_AUTH_URL, urllib.urlencode(params))
    logging.debug('Redirecting url=%r', target_url)
    return redirect(target_url)


@app.route(config.GOOGLE_OAUTH2_REDIRECT_PATH)
def login_auth():
    # TODO: Handle when the 'error' parameter is present
    params = dict(
        code=request.args.get('code'),
        client_id=config.GOOGLE_OAUTH2_CLIENT_ID,
        client_secret=config.GOOGLE_OAUTH2_CLIENT_SECRET,
        redirect_uri=config.GOOGLE_OAUTH2_REDIRECT_URI,
        grant_type='authorization_code'
    )
    payload = urllib.urlencode(params)
    logging.debug('Posting url=%r, payload=%r',
                  GOOGLE_OAUTH2_TOKEN_URL, payload)
    fetch_request = urllib2.Request(GOOGLE_OAUTH2_TOKEN_URL, payload)
    conn = urllib2.urlopen(fetch_request, timeout=FETCH_TIMEOUT_SECONDS)
    data = conn.read()
    result_dict = json.loads(data)

    params = dict(
        access_token=result_dict['access_token']
    )
    payload = urllib.urlencode(params)
    target_url = '%s?%s' % (GOOGLE_OAUTH2_USERINFO_URL, payload)
    logging.debug('Fetching url=%r', target_url)
    fetch_request = urllib2.Request(target_url)
    conn = urllib2.urlopen(fetch_request, timeout=FETCH_TIMEOUT_SECONDS)
    data = conn.read()
    result_dict = json.loads(data)

    user_id = '%s:%s' % (models.User.GOOGLE_OAUTH2, result_dict['id'])
    user = models.User.query.get(user_id)
    if not user:
        user = models.User(
            id=user_id,
            email_address=result_dict['email'])
        db.session.add(user)
        db.session.commit()

    login_user(user)

    return redirect(request.args.get('state'))


@app.route('/whoami')
@login_required
def debug_login():
    context = {
        'user': current_user,
    }
    return render_template('whoami.html', **context)



def superuser_required(f):
    """Requries the requestor to be a super user."""
    @functools.wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not (current_user.is_authenticated() and current_user.superuser):
            return abort(403)
        return f(*args, **kwargs)
    return wrapped
