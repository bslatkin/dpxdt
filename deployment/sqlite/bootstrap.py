#!/usr/bin/env python
# Copyright 2015 Brett Slatkin
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

"""Bootstraps a new installation by setting up the production environment."""

import os
os.environ['YOURAPPLICATION_SETTINGS'] = '../../settings.cfg'
os.environ['SQLITE_PRODUCTION'] = 'Yes'

from dpxdt.server import db
from dpxdt.server import models
from dpxdt.server import utils

db.create_all()

build = models.Build(name='Primary build')
db.session.add(build)
db.session.commit()

api_key = models.ApiKey(
    id=utils.human_uuid(),
    secret=utils.password_uuid(),
    purpose='Local workers',
    superuser=True,
    build_id=build.id)
db.session.add(api_key)
db.session.commit()

db.session.flush()

with open('flags.cfg', 'a') as f:
    f.write('--release_client_id=%s\n' % api_key.id)
    f.write('--release_client_secret=%s\n' % api_key.secret)
