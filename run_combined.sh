#!/bin/bash

source common.sh

./dpxdt/runserver.py \
    --local_queue_workers \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT \
    --pdiff_binary=$PDIFF_BINARY \
    --release_server_prefix=http://localhost:5000/api \
    --pdiff_queue_url=http://localhost:5000/api/work_queue/run-pdiff \
    --capture_queue_url=http://localhost:5000/api/work_queue/run-capture \
    $@
