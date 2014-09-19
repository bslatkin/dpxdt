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

"""Configuration for local development."""

import os
from secrets import *

SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI', 'sqlite:////tmp/test.db')

SERVER_NAME = os.environ.get('SERVER_NAME', None)
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# Google OAuth2 login config for local development.
GOOGLE_OAUTH2_EMAIL_ADDRESS = (
    '918724168220-nqq27o7so1p7stukds23oo2vof5gkfmh@'
    'developer.gserviceaccount.com')
GOOGLE_OAUTH2_REDIRECT_PATH = '/oauth2callback'
GOOGLE_OAUTH2_REDIRECT_URI = (
    'http://localhost:5000' + GOOGLE_OAUTH2_REDIRECT_PATH)
GOOGLE_OAUTH2_CLIENT_ID = (
    '918724168220-nqq27o7so1p7stukds23oo2vof5gkfmh.apps.googleusercontent.com')
GOOGLE_OAUTH2_CLIENT_SECRET = 'EhiCP-PuQYN0OsWGAELTUHyl'

CACHE_TYPE = 'simple'
CACHE_DEFAULT_TIMEOUT = 600

SESSION_COOKIE_DOMAIN = None

MAIL_DEFAULT_SENDER = 'Depicted <nobody@localhost>'
MAIL_SUPPRESS_SEND = True
MAIL_USE_APPENGINE = False
