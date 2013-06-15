#!/bin/bash

PYTHONPATH=./lib:$PYTHONPATH

./dpxdt/runworker.py --flagfile=flags.cfg
