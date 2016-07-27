#!/usr/local/bin/python

# Copyright 2016 Lindsey Simon
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This is a version of capture written to work with webdriver.
# Specifically, I've been testing with BrowserStack.
# Its configuration expectations are quite different from capture.js
# which is written for phantomjs.

# TODO(elsigh): Support cookies
# TODO(elsigh): Support resourcesToIgnore
# TODO(elsigh): Support httpUserName/httpPassWord
# TODO(elsigh): Support userAgent
# TODO(elsigh): Support injectCSS/injectJS

import json
import logging
from pprint import pprint
import sys
import time
from selenium import webdriver

config_file_path = sys.argv[1]
output_file = sys.argv[2]

with open(config_file_path) as config_file:
    config = json.load(config_file)
print "config: "
pprint(config)

assert config['command_executor']
command_executor = config['command_executor']
assert config['desired_capabilities']
desired_capabilities = config['desired_capabilities']
assert config['targetUrl']
target_url = config['targetUrl']


driver = webdriver.Remote(
    command_executor=config['command_executor'],
    desired_capabilities=config['desired_capabilities'],
)
driver.get(config['targetUrl'])
driver.save_screenshot(output_file)
driver.quit()
