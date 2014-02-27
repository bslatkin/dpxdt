#!/bin/bash

source common.sh

./dpxdt/tools/url_pair_diff.py \
    --release_server_prefix=$RELEASE_SERVER_PREFIX \
    "$@"
