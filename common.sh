#!/bin/bash

export PYTHONPATH=.:./dependencies/lib:$PYTHONPATH
export CAPTURE_SCRIPT=dpxdt/client/capture.js

# Update these for your environment:
export PHANTOMJS_BINARY=/Users/bslatkin/Downloads/phantomjs-1.9.0-macosx/bin/phantomjs

# Where the API servers to run workers against live.
export RELEASE_SERVER_PREFIX=http://localhost:5000/api
export QUEUE_SERVER_PREFIX=http://localhost:5000/api/work_queue

# Update this for your deployment environment:
export PHANTOMJS_DEPLOY_BINARY=/Users/bslatkin/Downloads/phantomjs-1.9.1-linux-x86_64/bin/phantomjs
