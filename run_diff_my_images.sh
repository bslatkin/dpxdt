#!/bin/bash

source common.sh

./dpxdt/tools/diff_my_images.py \
    --release_server_prefix=http://localhost:5000/api \
    "$@"
