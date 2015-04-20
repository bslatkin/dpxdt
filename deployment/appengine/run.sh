#!/bin/bash

gcloud \
    --project=dpxdt-local \
    preview app run \
    --host localhost:5000 \
    "$@" \
    combined_vm.yaml
