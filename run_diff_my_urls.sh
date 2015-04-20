#!/bin/bash

./dpxdt/tools/diff_my_urls.py \
    --release_server_prefix=http://localhost:5000/api \
    "$@"
