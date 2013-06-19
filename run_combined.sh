#!/bin/bash

source common.sh

./dpxdt/runserver.py \
    --local_queue_workers \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT \
    --release_server_prefix=http://localhost:5000/api \
    --queue_server_prefix=http://localhost:5000/api/work_queue \
    --reload_code \
    --port=5000 \
    --verbose \
    --ignore_auth \
    $@
