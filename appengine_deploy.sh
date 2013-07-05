#!/bin/bash

source common.sh

echo "Precompiling templates"
python -c \
    "from dpxdt.server import app; \
     app.jinja_env.compile_templates(
        './deployment/appengine/templates_compiled.zip')"

echo "Starting deployment"
appcfg.py update ./deployment/appengine
