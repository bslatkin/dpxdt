#!/bin/bash

gcloud \
    --project=dpxdt-local \
    preview app run \
    --enable-mvm-logs \
    --host localhost:5000 \
    combined_vm.yaml
