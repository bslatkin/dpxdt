#!/bin/bash

source common.sh

./dpxdt/client/site_diff.py \
    --release_server_prefix=http://localhost:5000/api \
    "$@"
