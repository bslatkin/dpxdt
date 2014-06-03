 #!/bin/bash

source common.sh

./dpxdt/runworker.py \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT \
    --release_server_prefix=$RELEASE_SERVER_PREFIX \
    --queue_server_prefix=$QUEUE_SERVER_PREFIX \
    --verbose \
    $@
