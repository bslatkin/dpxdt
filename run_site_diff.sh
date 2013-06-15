#!/bin/bash

# To run a very simple site diff when the local server is runnin, use:
#
# ./run_site_diff.sh \
#   --upload_build_id=2 \
#   --upload_release_name='blue' \
#   http://localhost:5000/static/dummy_page1.html

source common.sh

./dpxdt/client/site_diff.py \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT \
    --pdiff_binary=$PDIFF_BINARY \
    --release_server_prefix=http://localhost:5000/api \
    $@
