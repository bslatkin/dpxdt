# Copyright 2013 Google Inc. All Rights Reserved.

"""Tests for api_utils.py."""

import httplib
import os
import threading
import time
import unittest

import mock

from google.appengine.api import urlfetch
from google.appengine.runtime import apiproxy_errors


try:
  from cloudstorage import api_utils
  from cloudstorage import test_utils
except ImportError:
  from google.appengine.ext.cloudstorage import api_utils
  from google.appengine.ext.cloudstorage import test_utils


class RetryParamsTest(unittest.TestCase):
  """Tests for RetryParams."""

  def testValidation(self):
    self.assertRaises(TypeError, api_utils.RetryParams, 2)
    self.assertRaises(TypeError, api_utils.RetryParams, urlfetch_timeout='foo')
    self.assertRaises(TypeError, api_utils.RetryParams, max_retries=1.1)
    self.assertRaises(ValueError, api_utils.RetryParams, initial_delay=0)
    api_utils.RetryParams(backoff_factor=1)

  def testNoDelay(self):
    start_time = time.time()
    retry_params = api_utils.RetryParams(max_retries=0, min_retries=5)
    self.assertEqual(-1, retry_params.delay(1, start_time))
    retry_params = api_utils.RetryParams(max_retry_period=1, max_retries=1)
    self.assertEqual(-1, retry_params.delay(2, start_time - 2))

  def testMinRetries(self):
    start_time = time.time()
    retry_params = api_utils.RetryParams(min_retries=3,
                                         max_retry_period=10,
                                         initial_delay=1)
    with mock.patch('time.time') as t:
      t.return_value = start_time + 11
      self.assertEqual(1, retry_params.delay(1, start_time))

  def testPerThreadSetting(self):
    set_count = [0]
    cv = threading.Condition()

    retry_params1 = api_utils.RetryParams(max_retries=1000)
    retry_params2 = api_utils.RetryParams(max_retries=2000)
    retry_params3 = api_utils.RetryParams(max_retries=3000)

    def Target(retry_params):
      api_utils.set_default_retry_params(retry_params)
      with cv:
        set_count[0] += 1
        if set_count[0] != 3:
          cv.wait()
        cv.notify()
      self.assertEqual(retry_params, api_utils._get_default_retry_params())

    threading.Thread(target=Target, args=(retry_params1,)).start()
    threading.Thread(target=Target, args=(retry_params2,)).start()
    threading.Thread(target=Target, args=(retry_params3,)).start()

  def testPerRequestSetting(self):
    os.environ['REQUEST_LOG_ID'] = '1'
    retry_params = api_utils.RetryParams(max_retries=1000)
    api_utils.set_default_retry_params(retry_params)
    self.assertEqual(retry_params, api_utils._get_default_retry_params())

    os.environ['REQUEST_LOG_ID'] = '2'
    self.assertEqual(api_utils.RetryParams(),
                     api_utils._get_default_retry_params())

  def testDelay(self):
    start_time = time.time()
    retry_params = api_utils.RetryParams(backoff_factor=3,
                                         initial_delay=1,
                                         max_delay=28,
                                         max_retries=10,
                                         max_retry_period=100)
    with mock.patch('time.time') as t:
      t.return_value = start_time + 1
      self.assertEqual(1, retry_params.delay(1, start_time))
      self.assertEqual(3, retry_params.delay(2, start_time))
      self.assertEqual(9, retry_params.delay(3, start_time))
      self.assertEqual(27, retry_params.delay(4, start_time))
      self.assertEqual(28, retry_params.delay(5, start_time))
      self.assertEqual(28, retry_params.delay(6, start_time))
      t.return_value = start_time + 101
      self.assertEqual(-1, retry_params.delay(7, start_time))


class RetryFetchTest(unittest.TestCase):
  """Tests for _retry_fetch."""

  def setUp(self):
    super(RetryFetchTest, self).setUp()
    self.results = []
    self.max_retries = 10
    self.retry_params = api_utils.RetryParams(backoff_factor=1,
                                              max_retries=self.max_retries)

  def _SideEffect(self, *args, **kwds):
    if self.results:
      result = self.results.pop(0)
      if isinstance(result, Exception):
        raise result
      return result

  def testRetriableStatus(self):
    self.assertTrue(api_utils._should_retry(
        test_utils.MockUrlFetchResult(httplib.REQUEST_TIMEOUT, None, None)))
    self.assertTrue(api_utils._should_retry(
        test_utils.MockUrlFetchResult(555, None, None)))

  def testNoRetry(self):
    retry_params = api_utils.RetryParams(max_retries=0)
    self.assertEqual(None, api_utils._retry_fetch('foo', retry_params))

  def testRetrySuccess(self):
    self.results.append(test_utils.MockUrlFetchResult(httplib.REQUEST_TIMEOUT,
                                                      None, None))
    self.results.append(test_utils.MockUrlFetchResult(
        httplib.SERVICE_UNAVAILABLE, None, None))
    self.results.append(urlfetch.DownloadError())
    self.results.append(apiproxy_errors.Error())
    self.results.append(test_utils.MockUrlFetchResult(httplib.ACCEPTED,
                                                      None, None))
    with mock.patch.object(api_utils.urlfetch, 'fetch') as f:
      f.side_effect = self._SideEffect
      self.assertEqual(httplib.ACCEPTED,
                       api_utils._retry_fetch('foo', self.retry_params,
                                              deadline=1000).status_code)
      self.assertEqual(1000, f.call_args[1]['deadline'])

  def testRetryFailWithUrlfetchTimeOut(self):
    with mock.patch.object(api_utils.urlfetch, 'fetch') as f:
      f.side_effect = urlfetch.DownloadError
      try:
        api_utils._retry_fetch('foo', self.retry_params)
        self.fail('Should have raised error.')
      except urlfetch.DownloadError:
        self.assertEqual(self.max_retries, f.call_count)

  def testRetryFailWithResponseTimeOut(self):
    self.results.extend([urlfetch.DownloadError()] * (self.max_retries - 1))
    self.results.append(test_utils.MockUrlFetchResult(httplib.REQUEST_TIMEOUT,
                                                      None, None))
    with mock.patch.object(api_utils.urlfetch, 'fetch') as f:
      f.side_effect = self._SideEffect
      self.assertEqual(
          httplib.REQUEST_TIMEOUT,
          api_utils._retry_fetch('foo', self.retry_params).status_code)


if __name__ == '__main__':
  unittest.main()
