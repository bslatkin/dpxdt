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

"""Common flags for utility scripts."""

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

gflags.DEFINE_string(
    'upload_build_id', None,
    'ID of the build to upload this screenshot set to as a new release.')

gflags.DEFINE_string(
    'upload_release_name', None,
    'Along with upload_build_id, the name of the release to upload to. If '
    'not supplied, a new release will be created.')

gflags.DEFINE_string(
    'inject_css', None,
    'CSS to inject into all captured pages after they have loaded but '
    'before screenshotting.')

gflags.DEFINE_string(
    'inject_js', None,
    'JavaScript to inject into all captured pages after they have loaded '
    'but before screenshotting.')

gflags.DEFINE_string(
    'cookies', None,
    'Filename containing a JSON array of cookies to set.')

gflags.DEFINE_string(
    'release_cut_url', None,
    'URL that describes the release that you are testing. Usually a link to '
    'the commit or branch that was built.')

gflags.DEFINE_string(
    'tests_json_path', None,
    'Path to the JSON file containing the list of tests to diff.')
