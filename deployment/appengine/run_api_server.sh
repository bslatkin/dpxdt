#!/bin/bash

gcloud \
    --project=dpxdt-local \
    preview app run \
    --host localhost:5000 \
    "$@" \
    api_server.yaml
