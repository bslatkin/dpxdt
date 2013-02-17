#!/usr/bin/env python

"""TODO
"""

import logging
logging.getLogger().setLevel(logging.DEBUG)

import dpxdt

if __name__ == '__main__':
  dpxdt.app.run(debug=True, use_debugger=True)
