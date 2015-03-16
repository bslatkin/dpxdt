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

"""Entry point for the App Engine environment."""

# In the normal App Engine environment, this is always implicitly imported
# before the rest of the App. In the Managed VMs environment, it's not imported
# at all. So import it here. In normal App Engine this will be a no-op.
import appengine_config


import logging
import os

# Local modules
from dpxdt.server import app
from dpxdt.tools import run_server


@app.route('/_ah/warmup')
def appengine_warmup():
    return 'OK'


@app.route('/_ah/start')
def appengine_start():
    # TODO: Gracefully cancel this when /_ah/stop is received
    run_server.main([])


# Use the gae_mini_profiler module if it's importable.
try:
    import gae_mini_profiler.profiler
    import gae_mini_profiler.templatetags
except ImportError:
    logging.debug('gae_mini_profiler middleware could not be imported')
else:
    @app.context_processor
    def gae_mini_profiler_context():
        return dict(
            profiler_includes=gae_mini_profiler.templatetags.profiler_includes)
    app = gae_mini_profiler.profiler.ProfilerWSGIMiddleware(app)
