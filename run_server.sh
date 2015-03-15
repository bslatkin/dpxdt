#!/bin/bash

source common.sh

./dpxdt/tools/run_server.py \
    --enable_api_server \
    --reload_code \
    --port=5000 \
    --verbose \
    --ignore_auth \
    $@
