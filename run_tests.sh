#!/bin/bash

source common.sh

./tests/site_diff_test.py \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT \
    --pdiff_binary=$PDIFF_BINARY

./tests/workers_test.py
