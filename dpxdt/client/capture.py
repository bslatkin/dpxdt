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
# TODO(elsigh): Support injectHeaders

import json
import logging
from pprint import pprint
import sys
import time
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

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

# optional configs
resourceTimeoutMs = config.get('resourceTimeoutMs', 60 * 1000)

def getProfile(desired_capabilities, config):
    profile = None
    if desired_capabilities['browser'] == 'Firefox':
        profile  = webdriver.FirefoxProfile()
    if 'userAgent' in config and config['userAgent'] is not None and config['userAgent'] != '':
        profile.set_preference(
            'general.useragent.override', config['userAgent'])
        profile.update_preferences()
    return profile

def injectCSSandJS(driver, config):
    if 'injectCss' in config and config['injectCss'] is not None and config['injectCss'] != '':
        script = ("var node = document.createElement('style');"
                  "node.innerHTML = '%s';"
                  "document.body.appendChild(node);" % config['injectCss'])
        logging.info('injectCss script %s', script)
        driver.execute_script(script)
    if 'injectJs' in config and config['injectJs'] is not None and config['injectJs'] != '':
        driver.execute_script(config['injectJs'])


driver = webdriver.Remote(
    browser_profile=getProfile(desired_capabilities, config),
    command_executor=config['command_executor'],
    desired_capabilities=config['desired_capabilities'],
)
driver.get(config['targetUrl'])
injectCSSandJS(driver, config)

# Wait for any jQuery AJAX loading to finish.
wait = WebDriverWait(driver, resourceTimeoutMs)
areResourcesDoneScript = "return typeof jQuery !== 'undefined' && jQuery.active === 0"
wait.until(lambda driver: driver.execute_script(areResourcesDoneScript))

driver.save_screenshot(output_file)
driver.quit()
