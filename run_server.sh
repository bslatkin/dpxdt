#!/bin/bash

source common.sh

./dpxdt/runserver.py \
    --reload_code \
    --port=5000 \
    --verbose \
    $@
