#!/usr/bin/env python

"""TODO
"""

import logging
logging.getLogger().setLevel(logging.DEBUG)

import sightdiff

if __name__ == '__main__':
  sightdiff.app.run(debug=True, use_debugger=True)
