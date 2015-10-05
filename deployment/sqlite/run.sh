#!/bin/bash

source bin/activate
pip install -r requirements.txt
pip install -e .
trap "deactivate" 0

export YOURAPPLICATION_SETTINGS=../../settings.cfg
export SQLITE_PRODUCTION=Yes

dpxdt_server --flagfile=flags.cfg
