#!/bin/bash
export PYTHONPATH=./lib:$PYTHONPATH
./dpxdt/runworker.py --flagfile=flags.cfg
