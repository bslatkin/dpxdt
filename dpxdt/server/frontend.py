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

"""Frontend for the API server."""

import logging

# Local libraries
import flask
from flask import Flask, redirect, render_template, request, url_for
from flask.ext.wtf import Form

# Local modules
from . import app
from . import db
import forms
import models


@app.route('/')
def homepage():
    context = {
    }
    return render_template('home.html', **context)



@app.route('/new', methods=['GET', 'POST'])
def new_build():
    form = forms.BuildForm()
    if form.validate_on_submit():
        build_id = 1
        return redirect(url_for('build', id=build_id))

    return render_template(
        'new_build.html',
        build_form=form)


@app.route('/build')
def view_build():
    context = {
    }
    return render_template('view_build.html', **context)


@app.route('/release')
def view_release():
    context = {
    }
    return render_template('view_release.html', **context)


@app.route('/candidate')
def view_candidate():
    context = {
    }
    return render_template('view_candidate.html', **context)


@app.route('/run')
def view_run():
    context = {
    }
    return render_template('view_run.html', **context)
