#!/bin/bash

./dpxdt/tools/site_diff.py \
    --release_server_prefix=http://localhost:5000/api \
    "$@"
