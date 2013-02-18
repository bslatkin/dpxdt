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

"""TODO

PYTHONPATH=./lib:$PYTHONPATH \
./dpxdt/runserver.py \
    --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
    --phantomjs_script=path/to/client/capture.js \
    --pdiff_binary=path/to/pdiff/perceptualdiff
"""

import logging
logging.getLogger().setLevel(logging.DEBUG)

import server

if __name__ == '__main__':
    server.app.run(debug=True, use_debugger=True)
