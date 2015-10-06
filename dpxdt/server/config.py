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

"""Configuration for the server.

Defaults must enable local development.
"""

import base64
import hashlib
import os
import uuid

SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/test.db'

# Always set to None or else Flask will return 404s unless the inbound
# request perfectly matches this variable (including the port number).
SERVER_NAME = None

MAX_CONTENT_LENGTH = 16 * 1024 * 1024

SESSION_COOKIE_DOMAIN = None

# Google OAuth2 login config for local development.
GOOGLE_OAUTH2_REDIRECT_URI = 'http://localhost:5000/oauth2callback'

GOOGLE_OAUTH2_CLIENT_ID = (
    '918724168220-nqq27o7so1p7stukds23oo2vof5gkfmh.apps.googleusercontent.com')

GOOGLE_OAUTH2_CLIENT_SECRET = 'EhiCP-PuQYN0OsWGAELTUHyl'

CACHE_TYPE = 'simple'

CACHE_DEFAULT_TIMEOUT = 600

MAIL_DEFAULT_SENDER = 'Depicted <nobody@localhost>'

MAIL_SUPPRESS_SEND = True

# Cloud storage; currently only works in App Engine deployment
GOOGLE_CLOUD_STORAGE_BUCKET = None

SHOW_VIDEO_AND_PROMO_TEXT = False

# Secret key for CSRF key for WTForms, Login cookie. This will only last
# for the duration of the currently running process.
def default_key():
    return base64.b64encode(
        hashlib.sha1(uuid.uuid4().bytes).digest()).strip('=')

SECRET_KEY = default_key()
