#!/bin/bash

dev_appserver.py \
    --use_mtime_file_watcher=yes \
    --automatic_restart=yes \
    --mysql_user=root \
    --mysql_host=localhost \
    --mysql_port=3306 \
    --port=5000 \
    --log_level=debug \
    --require_indexes=yes \
    "$@" \
    api_server.yaml
