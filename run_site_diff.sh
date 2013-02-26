#!/bin/bash

source common.sh

./dpxdt/client/site_diff.py \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT \
    --pdiff_binary=$PDIFF_BINARY \
    --output_dir=/tmp/myoutputdir \
    --release_server_prefix=http://localhost:5000/api \
    $@
