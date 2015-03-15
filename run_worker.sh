 #!/bin/bash

source common.sh

./dpxdt/tools/run_server.py \
    --enable_queue_workers \
    --release_server_prefix=$RELEASE_SERVER_PREFIX \
    --queue_server_prefix=$QUEUE_SERVER_PREFIX \
    --verbose \
    $@
