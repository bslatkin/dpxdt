#!/bin/bash

source common.sh

./dpxdt/tools/site_diff.py \
    --release_server_prefix=$RELEASE_SERVER_PREFIX \
    "$@"
