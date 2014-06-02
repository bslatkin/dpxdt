#!/usr/bin/env python

# I always have trouble with virtualenv, pip, pkg_resources, etc, so this is
# a boostrapping script to workaround how flaky these tools are.

import sys
sys.path.insert(0, './dependencies/lib/')

import alembic.config

alembic.config.main()
