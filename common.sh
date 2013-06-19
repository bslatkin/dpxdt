#!/bin/bash

PYTHONPATH=./lib:$PYTHONPATH
CAPTURE_SCRIPT=dpxdt/client/capture.js

# Update these for your environment:
PHANTOMJS_BINARY=/Users/bslatkin/Downloads/phantomjs-1.9.0-macosx/bin/phantomjs

# Where the API servers to run workers against live.
RELEASE_SERVER_PREFIX=http://localhost:5000/api
QUEUE_SERVER_PREFIX=http://localhost:5000/api/work_queue

# Update this for your deployment environment:
PHANTOMJS_DEPLOY_BINARY=/Users/bslatkin/Downloads/phantomjs-1.9.1-linux-x86_64/bin/phantomjs
