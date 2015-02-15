#!/usr/bin/env python
# Copyright 2015 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utilities common to client modules."""

import logging
import os
import subprocess
import sys

# Local Libraries
import gflags
FLAGS = gflags.FLAGS


def verify_binary(flag_name, process_args=None):
    """Exits the program if the binary from the given flag doesn't run.

    Args:
        flag_name: Name of the flag that should be the path to the binary.
        process_args: Args to pass to the binary to do nothing but verify
            that it's working correctly (something like "--version") is good.
            Optional. Defaults to no args.

    Raises:
        SystemExit with error if the process did not work.
    """
    if process_args is None:
        process_args = []

    path = getattr(FLAGS, flag_name)
    if not path:
        logging.error('Flag %r not set' % flag_name)
        sys.exit(1)

    with open(os.devnull, 'w') as dev_null:
        try:
            subprocess.check_call(
                [path] + process_args,
                stdout=dev_null,
                stderr=subprocess.STDOUT)
        except:
            logging.exception('--%s binary at path %r does not work',
                              flag_name, path)
            sys.exit(1)
