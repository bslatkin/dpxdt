#!/usr/bin/env python
# Copyright 2014 Dan Vanderkam
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the local_pdiff tool."""

import unittest

from dpxdt.tools import local_pdiff

class LocalPdiffTest(unittest.TestCase):
    """Tests for the Local PDiff tool."""

    def setUp(self):
        """Sets up the test harness."""
        pass

    def testShouldRunTest(self):
        should_run = local_pdiff.should_run_test
        self.assertTrue(should_run('foo', ''))  # empty string = anything goes.
        self.assertTrue(should_run('foo', '*'))  # run everything
        self.assertTrue(should_run('fooBar', 'foo*'))
        self.assertTrue(should_run('fooFoo', 'foo*'))
        self.assertFalse(should_run('barfoo', 'foo*'))
        self.assertTrue(should_run('barfoo', '*foo*'))
        self.assertTrue(should_run('foo', '*foo*:*bar*'))
        self.assertTrue(should_run('bar', '*foo*:*bar*'))
        self.assertFalse(should_run('baz', '*foo*:*bar*'))

        self.assertTrue(should_run('baz', '-*no*'))
        self.assertFalse(should_run('nobaz', '-*no*'))
        self.assertFalse(should_run('bazno', '-*no*'))
        self.assertFalse(should_run('banoz', '-*no*'))

        self.assertFalse(should_run('foo.bar', 'foo.*-foo.bar'))
        self.assertTrue(should_run('foo.baz', 'foo.*-foo.bar'))
        self.assertFalse(should_run('foobaz', 'foo.*-foo.bar'))


if __name__ == '__main__':
    unittest.main()
