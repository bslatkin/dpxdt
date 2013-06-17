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
import flask
from flask import abort, redirect, render_template, request, url_for
from flask.ext.login import (
    current_user, fresh_login_required, login_required,
    login_user, logout_user)

# Local modules
from . import app
from . import db
from . import login
import config
import forms
import models
import utils


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
    next_url = request.args.get('next', default='/', type=str)

    if app.config.get('IGNORE_AUTH'):
        fake_id = 'anonymous_superuser'
        anonymous_superuser = models.User.query.get(fake_id)
        if not anonymous_superuser:
            anonymous_superuser = models.User(
                id=fake_id,
                email_address='superuser@example.com',
                superuser=1)
            db.session.add(anonymous_superuser);
            db.session.commit()
        login_user(anonymous_superuser)
        return redirect(next_url)

    # Inspired by:
    #   http://stackoverflow.com/questions/9499286
    #   /using-google-oauth2-with-flask
    params = dict(
        response_type='code',
        client_id=config.GOOGLE_OAUTH2_CLIENT_ID,
        redirect_uri=config.GOOGLE_OAUTH2_REDIRECT_URI,
        scope=GOOGLE_OAUTH2_SCOPES,
        state=urllib.quote(next_url),
    )
    target_url = '%s?%s' % (
        GOOGLE_OAUTH2_AUTH_URL, urllib.urlencode(params))
    logging.debug('Redirecting user to login at url=%r', target_url)
    return redirect(target_url)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('homepage'))


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
    logging.debug('Posting for token to url=%r, payload=%r',
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
    logging.debug('Fetching user info from url=%r', target_url)
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
    final_url = urllib.unquote(request.args.get('state'))
    logging.debug('User is logged in. Redirecting to url=%r', final_url)
    return redirect(final_url)


@app.route('/whoami')
@login_required
def debug_login():
    return render_template(
        'whoami.html', user=current_user)


def superuser_required(f):
    """Requires the requestor to be a super user."""
    @functools.wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if not (current_user.is_authenticated() and current_user.superuser):
            abort(403)
        return f(*args, **kwargs)
    return wrapped


def can_user_access_build(param_name):
    """Determines if the current user can access the build ID in the request.

    Args:
        param_name: Parameter name to use for getting the build ID from the
            request. Will fetch from GET or POST requests.

    Returns:
        The build the user has access to.
    """
    build_id = (
        request.args.get(param_name, type=int) or
        request.form.get(param_name, type=int))
    if not build_id:
        logging.debug('Build ID in param_name=%r was missing', param_name)
        abort(400)

    build = models.Build.query.get(build_id)
    if not build:
        logging.debug('Could not find build_id=%r', build_id)
        abort(404)

    user_is_owner = False

    if current_user.is_authenticated():
        user_is_owner = build.owners.filter_by(
            id=current_user.get_id()).first()

    if not user_is_owner:
        if request.method != 'GET':
            logging.debug('No way to log in user via modifying request')
            abort(403)
        elif build.public:
            pass
        elif current_user.is_authenticated():
            logging.debug('User must authenticate to see non-public build')
            abort(403)
        else:
            logging.debug('Redirecting user to login to get build access')
            abort(login.unauthorized())

    return build


def build_access_required(function_or_param_name):
    """Decorator ensures user has access to the build ID in the request.

    May be used in two ways:

        @build_access_required
        def my_func(build):
            ...

        @build_access_required('custom_build_id_param')
        def my_func(build):
            ...

    Always calls the given function with the models.Build entity as the
    first positional argument.
    """
    def get_wrapper(param_name, f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            build = can_user_access_build(param_name)
            return f(build, *args, **kwargs)
        return wrapped

    if isinstance(function_or_param_name, basestring):
        return lambda f: get_wrapper(function_or_param_name, f)
    else:
        return get_wrapper('id', function_or_param_name)


def current_api_key():
    """Determines the API key for the current request.

    Returns:
        The API key.
    """
    if app.config.get('IGNORE_AUTH'):
        return models.ApiKey(
            id='anonymous_superuser',
            secret='',
            superuser=True)

    auth_header = request.authorization
    if not auth_header:
        logging.debug('API request lacks authorization header')
        abort(flask.Response(
            'API key required', 401,
            {'WWW-Authenticate': 'Basic realm="API key required"'}))

    api_key = models.ApiKey.query.get(auth_header.username)
    utils.jsonify_assert(api_key, 'API key must exist', 403)
    utils.jsonify_assert(api_key.active, 'API key must be active', 403)
    utils.jsonify_assert(api_key.secret == auth_header.password,
                         'Must have good credentials', 403)

    logging.debug('Authenticated as API key=%r', api_key.id)

    return api_key


def can_api_key_access_build(param_name):
    """Determines if the current API key can access the build in the request.

    Args:
        param_name: Parameter name to use for getting the build ID from the
            request. Will fetch from GET or POST requests.

    Returns:
        The Build the API key has access to.
    """
    api_key = current_api_key()
    build_id = (
        request.args.get(param_name, type=int) or
        request.form.get(param_name, type=int))
    utils.jsonify_assert(build_id, 'build_id required')
    build = models.Build.query.get(build_id)
    utils.jsonify_assert(build is not None, 'build must exist', 404)

    if not api_key.superuser:
        utils.jsonify_assert(api_key.build_id == build_id,
                             'API key must have access', 404)

    return build


def build_api_access_required(f):
    """Decorator ensures API key has access to the build ID in the request.

    Always calls the given function with the models.Build entity as the
    first positional argument.
    """
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        build = can_api_key_access_build('build_id')
        return f(build, *args, **kwargs)
    return wrapped


def superuser_api_key_required(f):
    """Decorator ensures only superuser API keys can request this function."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        api_key = current_api_key()

        utils.jsonify_assert(
            api_key.superuser,
            'API key=%r must be a super user' % api_key.id,
            403)

        return f(*args, **kwargs)

    return wrapped


@app.route('/api_keys', methods=['GET', 'POST'])
@fresh_login_required
@build_access_required('build_id')
def manage_api_keys(build):
    """Page for viewing and creating API keys."""
    create_form = forms.CreateApiKeyForm()
    if create_form.validate_on_submit():
        api_key = models.ApiKey()
        create_form.populate_obj(api_key)
        api_key.id = utils.human_uuid()
        api_key.secret = utils.password_uuid()
        db.session.add(api_key)
        db.session.commit()

        logging.info('Created API key=%r for build_id=%r',
                     api_key.id, build.id)
        return redirect(url_for('manage_api_keys', build_id=build.id))

    create_form.build_id.data = build.id

    api_key_query = (
        models.ApiKey.query
        .filter_by(build_id=build.id)
        .order_by(models.ApiKey.created.desc())
        .limit(1000))

    revoke_form_list = []
    for api_key in api_key_query:
        form = forms.RevokeApiKeyForm()
        form.id.data = api_key.id
        form.build_id.data = build.id
        form.revoke.data = True
        revoke_form_list.append((api_key, form))

    return render_template(
        'view_api_keys.html',
        build=build,
        create_form=create_form,
        revoke_form_list=revoke_form_list)


@app.route('/api_keys.revoke', methods=['POST'])
@fresh_login_required
@build_access_required('build_id')
def revoke_api_key(build):
    """Form submission handler for revoking API keys."""
    form = forms.RevokeApiKeyForm()
    if form.validate_on_submit():
        api_key = models.ApiKey.query.get(form.id.data)
        if api_key.build_id != build.id:
            logging.debug('User does not have access to API key=%r',
                          api_key.id)
            abort(403)

        api_key.active = False
        db.session.add(api_key)
        db.session.commit()

    return redirect(url_for('manage_api_keys', build_id=build.id))
