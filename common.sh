#!/bin/bash

PYTHONPATH=./lib:$PYTHONPATH
CAPTURE_SCRIPT=dpxdt/client/capture.js

# Update these for your testing environment:
PHANTOMJS_BINARY=/Users/bslatkin/Downloads/phantomjs-1.9.0-macosx/bin/phantomjs
PDIFF_BINARY=/Users/bslatkin/projects/dpxdt/pdiff/perceptualdiff

# Where the API servers to run workers against live.
RELEASE_SERVER_PREFIX=http://localhost:5000/api
QUEUE_SERVER_PREFIX=http://localhost:5000/api/work_queue

# Update these for your deployment environment:
PHANTOMJS_DEPLOY_BINARY=/Users/bslatkin/Downloads/phantomjs-1.9.0-macosx/bin/phantomjs
PDIFF_DEPLOY_BINARY=/Users/bslatkin/projects/dpxdt/pdiff/perceptualdiff.linux
