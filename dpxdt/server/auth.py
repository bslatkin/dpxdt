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

import datetime
import functools
import json
import logging
import time
import urllib
import urllib2

# Local libraries
import flask
from flask import abort, g, redirect, render_template, request, url_for
from flask.ext.login import (
    confirm_login, current_user, fresh_login_required, login_fresh,
    login_required, login_user, logout_user)

# Local modules
from . import app
from . import db
from . import login
import config
from dpxdt.server import forms
from dpxdt.server import models
from dpxdt.server import operations
from dpxdt.server import utils

GOOGLE_OAUTH2_AUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_OAUTH2_TOKEN_URL = 'https://accounts.google.com/o/oauth2/token'
GOOGLE_OAUTH2_USERINFO_URL = 'https://www.googleapis.com/oauth2/v1/userinfo'
GOOGLE_OAUTH2_SCOPES ='https://www.googleapis.com/auth/userinfo.email'
FETCH_TIMEOUT_SECONDS = 60


@login.user_loader
def load_user(user_id):
    user = operations.UserOps(user_id).load()
    if user and user.is_authenticated():
        logging.debug('Authenticated as user=%r', user.get_id())
    return user


@app.context_processor
def auth_context():
    """Adds extra default context for rendered templates."""
    return dict(current_user=current_user)


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
            db.session.add(anonymous_superuser)
            db.session.commit()
        login_user(anonymous_superuser)
        confirm_login()
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
    logging.debug('Result user info dict: %r', result_dict)
    email_address = result_dict['email']

    if not result_dict['verified_email']:
        abort(flask.Response('Your email address must be verified', 403))

    user_id = '%s:%s' % (models.User.GOOGLE_OAUTH2, result_dict['id'])
    user = models.User.query.get(user_id)
    if not user:
        user = models.User(id=user_id)

    # Email address on the account may change, user ID will stay the same.
    # Do not allow the user to claim existing build invitations with their
    # old email address.
    if user.email_address != email_address:
        user.email_address = email_address

    user.last_seen = datetime.datetime.utcnow()

    db.session.add(user)
    db.session.commit()

    login_user(user)
    confirm_login()

    # Clear all flashed messages from the session on login.
    flask.get_flashed_messages()

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

    ops = operations.UserOps(current_user.get_id())
    build, user_is_owner = ops.owns_build(build_id)
    if not build:
        logging.debug('Could not find build_id=%r', build_id)
        abort(404)

    if current_user.is_authenticated() and not user_is_owner:
        # Assume the user should be able to access the build but can't because
        # the cache is out of date. This forces the cache to repopulate, any
        # outstanding user invitations to be completed, hopefully resulting in
        # the user having access to the build.
        ops.evict()
        claim_invitations(current_user)
        build, user_is_owner = ops.owns_build(build_id)

    if not user_is_owner:
        if current_user.is_authenticated() and current_user.superuser:
            pass
        elif request.method != 'GET':
            logging.debug('No way to log in user via modifying request')
            abort(403)
        elif build.public:
            pass
        elif current_user.is_authenticated():
            logging.debug('User does not have access to this build')
            abort(flask.Response('You cannot access this build', 403))
        else:
            logging.debug('Redirecting user to login to get build access')
            abort(login.unauthorized())
    elif not login_fresh():
        logging.debug('User login is old; forcing refresh')
        abort(login.needs_refresh())

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
            g.build = can_user_access_build(param_name)
            if not utils.is_production():
                # Insert a sleep to emulate page loading in production.
                time.sleep(0.5)
            return f(*args, **kwargs)
        return wrapped

    if isinstance(function_or_param_name, basestring):
        return lambda f: get_wrapper(function_or_param_name, f)
    else:
        return get_wrapper('id', function_or_param_name)


def _get_api_key_ops():
    """Gets the operations.ApiKeyOps instance for the current request."""
    auth_header = request.authorization
    if not auth_header:
        logging.debug('API request lacks authorization header')
        abort(flask.Response(
            'API key required', 401,
            {'WWW-Authenticate': 'Basic realm="API key required"'}))

    return operations.ApiKeyOps(auth_header.username, auth_header.password)


def current_api_key():
    """Determines the API key for the current request.

    Returns:
        The ApiKey instance.
    """
    if app.config.get('IGNORE_AUTH'):
        return models.ApiKey(
            id='anonymous_superuser',
            secret='',
            superuser=True)

    ops = _get_api_key_ops()
    api_key = ops.get()
    logging.debug('Authenticated as API key=%r', api_key.id)

    return api_key


def can_api_key_access_build(param_name):
    """Determines if the current API key can access the build in the request.

    Args:
        param_name: Parameter name to use for getting the build ID from the
            request. Will fetch from GET or POST requests.

    Returns:
        (api_key, build) The API Key and the Build it has access to.
    """
    build_id = (
        request.args.get(param_name, type=int) or
        request.form.get(param_name, type=int))
    utils.jsonify_assert(build_id, 'build_id required')

    if app.config.get('IGNORE_AUTH'):
        api_key = models.ApiKey(
            id='anonymous_superuser',
            secret='',
            superuser=True)
        build = models.Build.query.get(build_id)
        utils.jsonify_assert(build is not None, 'build must exist', 404)
    else:
        ops = _get_api_key_ops()
        api_key, build = ops.can_access_build(build_id)

    return api_key, build


def build_api_access_required(f):
    """Decorator ensures API key has access to the build ID in the request.

    Always calls the given function with the models.Build entity as the
    first positional argument.
    """
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        g.api_key, g.build = can_api_key_access_build('build_id')
        return f(*args, **kwargs)
    return wrapped


def superuser_api_key_required(f):
    """Decorator ensures only superuser API keys can request this function."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        api_key = current_api_key()
        g.api_key = api_key

        utils.jsonify_assert(
            api_key.superuser,
            'API key=%r must be a super user' % api_key.id,
            403)

        return f(*args, **kwargs)

    return wrapped


@app.route('/api_keys', methods=['GET', 'POST'])
@fresh_login_required
@build_access_required('build_id')
def manage_api_keys():
    """Page for viewing and creating API keys."""
    build = g.build
    create_form = forms.CreateApiKeyForm()
    if create_form.validate_on_submit():
        api_key = models.ApiKey()
        create_form.populate_obj(api_key)
        api_key.id = utils.human_uuid()
        api_key.secret = utils.password_uuid()

        save_admin_log(build, created_api_key=True, message=api_key.id)

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
def revoke_api_key():
    """Form submission handler for revoking API keys."""
    build = g.build
    form = forms.RevokeApiKeyForm()
    if form.validate_on_submit():
        api_key = models.ApiKey.query.get(form.id.data)
        if api_key.build_id != build.id:
            logging.debug('User does not have access to API key=%r',
                          api_key.id)
            abort(403)

        api_key.active = False
        save_admin_log(build, revoked_api_key=True, message=api_key.id)

        db.session.add(api_key)
        db.session.commit()

        ops = operations.ApiKeyOps(api_key.id, api_key.secret)
        ops.evict()

    return redirect(url_for('manage_api_keys', build_id=build.id))


def claim_invitations(user):
    """Claims any pending invitations for the given user's email address."""
    # See if there are any build invitations present for the user with this
    # email address. If so, replace all those invitations with the real user.
    invitation_user_id = '%s:%s' % (
        models.User.EMAIL_INVITATION, user.email_address)
    invitation_user = models.User.query.get(invitation_user_id)
    if invitation_user:
        invited_build_list = list(invitation_user.builds)
        if not invited_build_list:
            return

        db.session.add(user)
        logging.debug('Found %d build admin invitations for id=%r, user=%r',
                      len(invited_build_list), invitation_user_id, user)

        for build in invited_build_list:
            build.owners.remove(invitation_user)
            if not build.is_owned_by(user.id):
                build.owners.append(user)
                logging.debug('Claiming invitation for build_id=%r', build.id)
                save_admin_log(build, invite_accepted=True)
            else:
                logging.debug('User already owner of build. '
                              'id=%r, build_id=%r', user.id, build.id)
            db.session.add(build)

        db.session.delete(invitation_user)
        db.session.commit()
        # Re-add the user to the current session so we can query with it.
        db.session.add(current_user)


@app.route('/admins', methods=['GET', 'POST'])
@fresh_login_required
@build_access_required('build_id')
def manage_admins():
    """Page for viewing and managing build admins."""
    build = g.build

    # Do not show cached data
    db.session.add(build)
    db.session.refresh(build)

    add_form = forms.AddAdminForm()
    if add_form.validate_on_submit():

        invitation_user_id = '%s:%s' % (
            models.User.EMAIL_INVITATION, add_form.email_address.data)

        invitation_user = models.User.query.get(invitation_user_id)
        if not invitation_user:
            invitation_user = models.User(
                id=invitation_user_id,
                email_address=add_form.email_address.data)
            db.session.add(invitation_user)

        db.session.add(build)
        db.session.add(invitation_user)
        db.session.refresh(build, lockmode='update')

        build.owners.append(invitation_user)
        save_admin_log(build, invited_new_admin=True,
                       message=invitation_user.email_address)

        db.session.commit()

        logging.info('Added user=%r as owner to build_id=%r',
                     invitation_user.id, build.id)
        return redirect(url_for('manage_admins', build_id=build.id))

    add_form.build_id.data = build.id

    revoke_form_list = []
    for user in build.owners:
        form = forms.RemoveAdminForm()
        form.user_id.data = user.id
        form.build_id.data = build.id
        form.revoke.data = True
        revoke_form_list.append((user, form))

    return render_template(
        'view_admins.html',
        build=build,
        add_form=add_form,
        revoke_form_list=revoke_form_list)


@app.route('/admins.revoke', methods=['POST'])
@fresh_login_required
@build_access_required('build_id')
def revoke_admin():
    """Form submission handler for revoking admin access to a build."""
    build = g.build
    form = forms.RemoveAdminForm()
    if form.validate_on_submit():
        user = models.User.query.get(form.user_id.data)
        if not user:
            logging.debug('User being revoked admin access does not exist.'
                          'id=%r, build_id=%r', form.user_id.data, build.id)
            abort(400)

        if user == current_user:
            logging.debug('User trying to remove themself as admin. '
                          'id=%r, build_id=%r', user.id, build.id)
            abort(400)

        db.session.add(build)
        db.session.add(user)
        db.session.refresh(build, lockmode='update')
        db.session.refresh(user, lockmode='update')

        user_is_owner = build.owners.filter_by(id=user.id)
        if not user_is_owner:
            logging.debug('User being revoked admin access is not owner. '
                          'id=%r, build_id=%r.', user.id, build.id)
            abort(400)

        build.owners.remove(user)
        save_admin_log(build, revoked_admin=True, message=user.email_address)

        db.session.commit()

        operations.UserOps(user.get_id()).evict()

    return redirect(url_for('manage_admins', build_id=build.id))


def save_admin_log(build, **kwargs):
    """Saves an action to the admin log."""
    message = kwargs.pop('message', None)
    release = kwargs.pop('release', None)
    run = kwargs.pop('run', None)

    if not len(kwargs) == 1:
        raise TypeError('Must specify a LOG_TYPE argument')

    log_enum = kwargs.keys()[0]
    log_type = getattr(models.AdminLog, log_enum.upper(), None)
    if not log_type:
        raise TypeError('Bad log_type argument: %s' % log_enum)

    if current_user.is_anonymous():
        user_id = None
    else:
        user_id = current_user.get_id()

    log = models.AdminLog(
        build_id=build.id,
        log_type=log_type,
        message=message,
        user_id=user_id)

    if release:
        log.release_id = release.id

    if run:
        log.run_id = run.id
        log.release_id = run.release_id

    db.session.add(log)


@app.route('/activity')
@fresh_login_required
@build_access_required('build_id')
def view_admin_log():
    """Page for viewing the log of admin activity."""
    build = g.build

    # TODO: Add paging

    log_list = (
        models.AdminLog.query
        .filter_by(build_id=build.id)
        .order_by(models.AdminLog.created.desc())
        .all())

    return render_template(
        'view_admin_log.html',
        build=build,
        log_list=log_list)
