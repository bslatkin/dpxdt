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

"""Forms for parsing and validating frontend requests."""

import datetime

# Local libraries
from flask.ext.wtf import (
    BooleanField, DataRequired, Email, Form, HiddenField, IntegerField,
    Length, NumberRange, Optional, Required, SubmitField, TextField)

# Local modules
from . import app


class BuildForm(Form):
    """Form for creating or editing a build."""

    name = TextField(validators=[Length(min=1, max=200)])


class ReleaseForm(Form):
    """Form for viewing or approving a release."""

    id = HiddenField(validators=[NumberRange(min=1)])
    name = HiddenField(validators=[Length(min=1, max=200)])
    number = HiddenField(validators=[NumberRange(min=1)])

    good = HiddenField()
    bad = HiddenField()
    reviewing = HiddenField()


class RunForm(Form):
    """Form for viewing or approving a run."""

    id = HiddenField(validators=[NumberRange(min=1)])
    name = HiddenField(validators=[Length(min=1, max=200)])
    number = HiddenField(validators=[NumberRange(min=1)])
    test = HiddenField(validators=[Length(min=1, max=200)])
    type = HiddenField(validators=[Length(min=1, max=200)])
    approve = HiddenField()
    disapprove = HiddenField()


class CreateApiKeyForm(Form):
    """Form for creating an API key."""

    build_id = HiddenField(validators=[NumberRange(min=1)])
    purpose = TextField('Purpose', validators=[Length(min=1, max=200)])
    create = SubmitField('Create')


class RevokeApiKeyForm(Form):
    """Form for revoking an API key."""

    id = HiddenField()
    build_id = HiddenField(validators=[NumberRange(min=1)])
    revoke = SubmitField('Revoke')


class AddAdminForm(Form):
    """Form for adding a build admin."""

    email_address = TextField('Email address',
                              validators=[Length(min=1, max=200)])
    build_id = HiddenField(validators=[NumberRange(min=1)])
    add = SubmitField('Add')


class RemoveAdminForm(Form):
    """Form for removing a build admin."""

    user_id = HiddenField(validators=[Length(min=1, max=200)])
    build_id = HiddenField(validators=[NumberRange(min=1)])
    revoke = SubmitField('Revoke')


class ModifyWorkQueueTaskForm(Form):
    """Form for modifying a work queue task."""

    task_id = HiddenField()
    action = HiddenField()
    delete = SubmitField('Delete')
    retry = SubmitField('Retry')


class SettingsForm(Form):
    """Form for modifying build settings."""

    name = TextField(validators=[Length(min=1, max=200)])
    send_email = BooleanField('Send notification emails')
    email_alias = TextField('Mailing list for notifications',
                            validators=[Optional(), Email()])
    build_id = HiddenField(validators=[NumberRange(min=1)])
    save = SubmitField('Save')
