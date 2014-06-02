#!/bin/bash

# Terminate immediately with an error if any child command fails.
set -e

source common.sh

./tests/site_diff_test.py \
    --phantomjs_binary=$PHANTOMJS_BINARY \
    --phantomjs_script=$CAPTURE_SCRIPT

./tests/workers_test.py
