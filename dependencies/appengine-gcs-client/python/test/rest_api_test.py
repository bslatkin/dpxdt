# Copyright 2012 Google Inc. All Rights Reserved.




import httplib
import pickle
import unittest
import mock

from google.appengine.ext import ndb
from google.appengine.api import urlfetch
from google.appengine.ext import testbed

try:
  from cloudstorage import api_utils
  from cloudstorage import rest_api
  from cloudstorage import test_utils
except ImportError:
  from google.appengine.ext.cloudstorage import api_utils
  from google.appengine.ext.cloudstorage import rest_api
  from google.appengine.ext.cloudstorage import test_utils


class RestApiTest(unittest.TestCase):

  def setUp(self):
    super(RestApiTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_app_identity_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_urlfetch_stub()
    api_utils._thread_local_settings.retry_params = None

  def tearDown(self):
    self.testbed.deactivate()
    super(RestApiTest, self).tearDown()

  def testBasicCall(self):
    api = rest_api._RestApi('scope')
    self.assertEqual(api.scopes, ['scope'])

    fut_get_token = ndb.Future()
    fut_get_token.set_result('blah')
    api.get_token_async = mock.create_autospec(api.get_token_async,
                                               return_value=fut_get_token)

    fut_urlfetch = ndb.Future()
    fut_urlfetch.set_result(
        test_utils.MockUrlFetchResult(200, {'foo': 'bar'}, 'yoohoo'))
    api.urlfetch_async = mock.create_autospec(api.urlfetch_async,
                                              return_value=fut_urlfetch)

    res = api.do_request('http://example.com')

    self.assertEqual(res, (200, {'foo': 'bar'}, 'yoohoo'))
    api.urlfetch_async.assert_called_once_with(
        'http://example.com',
        headers={'authorization': 'OAuth blah'},
        follow_redirects=False,
        payload=None,
        method='GET',
        deadline=None,
        callback=None)

  def testAsyncCall(self):
    api = rest_api._RestApi('scope')

    fut_urlfetch = ndb.Future()
    fut_urlfetch.set_result(
        test_utils.MockUrlFetchResult(200, {'foo': 'bar'}, 'yoohoo'))
    api.urlfetch_async = mock.create_autospec(api.urlfetch_async,
                                              return_value=fut_urlfetch)

    fut = api.do_request_async('http://example.com')
    res = fut.get_result()

    self.assertEqual(res, (200, {'foo': 'bar'}, 'yoohoo'))
    api.urlfetch_async.assert_called_once_with(
        'http://example.com',
        headers=mock.ANY,
        follow_redirects=False,
        payload=None,
        method='GET',
        deadline=None,
        callback=None)

  def testMultipleScopes(self):
    api = rest_api._RestApi(['scope1', 'scope2'])
    self.assertEqual(api.scopes, ['scope1', 'scope2'])

  def testNegativeTimeout(self):
    api = rest_api._RestApi('scope')
    fut1 = ndb.Future()
    fut1.set_result(('token1', 0))
    fut2 = ndb.Future()
    fut2.set_result(('token2', 0))
    api.make_token_async = mock.create_autospec(
        api.make_token_async, side_effect=[fut1, fut2])
    token1 = api.get_token()
    api.token = None
    token2 = api.get_token()
    self.assertNotEqual(token1, token2)

  def testTokenMemoized(self):
    api = rest_api._RestApi('scope')
    self.assertEqual(api.token, None)
    t1 = api.get_token()
    self.assertEqual(api.token, t1)
    t2 = api.get_token()
    self.assertEqual(t2, t1)

    t3 = api.get_token(refresh=True)
    self.assertNotEqual(t2, t3)
    self.assertEqual(api.token, t3)

  def testDifferentServiceAccounts(self):
    api1 = rest_api._RestApi('scope', 123)
    api2 = rest_api._RestApi('scope', 456)

    t1 = api1.get_token()
    t2 = api2.get_token()
    self.assertNotEqual(t1, t2)

  def testSameServiceAccount(self):
    api1 = rest_api._RestApi('scope', 123)
    api2 = rest_api._RestApi('scope', 123)

    t1 = api1.get_token()
    t2 = api2.get_token()
    self.assertEqual(t1, t2)

  def testRefreshToken(self):
    api = rest_api._RestApi('scope')

    fut_get_token1 = ndb.Future()
    fut_get_token1.set_result('blah')
    fut_get_token2 = ndb.Future()
    fut_get_token2.set_result('bleh')

    api.get_token_async = mock.create_autospec(
        api.get_token_async,
        side_effect=[fut_get_token1, fut_get_token2])

    fut_urlfetch1 = ndb.Future()
    fut_urlfetch1.set_result(test_utils.MockUrlFetchResult(401, {}, ''))
    fut_urlfetch2 = ndb.Future()
    fut_urlfetch2.set_result(
        test_utils.MockUrlFetchResult(200, {'foo': 'bar'}, 'yoohoo'))

    api.urlfetch_async = mock.create_autospec(
        api.urlfetch_async,
        side_effect=[fut_urlfetch1, fut_urlfetch2])

    res = api.do_request('http://example.com')

    self.assertEqual(res, (200, {'foo': 'bar'}, 'yoohoo'))

    self.assertEqual(api.urlfetch_async.call_args_list,
                     [mock.call('http://example.com',
                                headers={'authorization': 'OAuth bleh'},
                                follow_redirects=False,
                                payload=None,
                                method='GET',
                                deadline=None,
                                callback=None),
                      mock.call('http://example.com',
                                headers={'authorization': 'OAuth bleh'},
                                follow_redirects=False,
                                payload=None,
                                method='GET',
                                deadline=None,
                                callback=None)])

  def testCallUrlFetch(self):
    api = rest_api._RestApi('scope')

    fut = ndb.Future()
    fut.set_result(test_utils.MockUrlFetchResult(200, {}, 'response'))
    ndb.Context.urlfetch = mock.create_autospec(
        ndb.Context.urlfetch,
        return_value=fut)

    res = api.urlfetch('http://example.com', method='PUT', headers={'a': 'b'})

    self.assertEqual(res.status_code, 200)
    self.assertEqual(res.content, 'response')

  def testPickling(self):
    retry_params = api_utils.RetryParams(max_retries=1000)
    api = rest_api._RestApi('scope', service_account_id=1,
                            retry_params=retry_params)
    self.assertNotEqual(None, api.get_token())

    pickled_api = pickle.loads(pickle.dumps(api))
    self.assertEqual(0, len(set(api.__dict__.keys()) ^
                            set(pickled_api.__dict__.keys())))
    for k, v in api.__dict__.iteritems():
      if not hasattr(v, '__call__'):
        self.assertEqual(v, pickled_api.__dict__[k])

    pickled_api.token = None

    fut_urlfetch = ndb.Future()
    fut_urlfetch.set_result(
        test_utils.MockUrlFetchResult(200, {'foo': 'bar'}, 'yoohoo'))
    pickled_api.urlfetch_async = mock.create_autospec(
        pickled_api.urlfetch_async, return_value=fut_urlfetch)

    res = pickled_api.do_request('http://example.com')
    self.assertEqual(res, (200, {'foo': 'bar'}, 'yoohoo'))

  def testRetryAfterDoRequestUrlFetchTimeout(self):
    api = rest_api._RestApi('scope')

    fut = ndb.Future()
    fut.set_exception(urlfetch.DownloadError())
    ndb.Context.urlfetch = mock.create_autospec(
        ndb.Context.urlfetch,
        return_value=fut)

    with mock.patch('google.appengine.api.urlfetch'
                    '.fetch') as f:
      f.return_value = test_utils.MockUrlFetchResult(httplib.ACCEPTED,
                                                     None, None)
      self.assertEqual(httplib.ACCEPTED, api.do_request('foo')[0])

  def testRetryAfterNoRequsetResponseTimeout(self):
    api = rest_api._RestApi('scope')

    fut = ndb.Future()
    fut.set_result(test_utils.MockUrlFetchResult(httplib.REQUEST_TIMEOUT,
                                                 None, None))
    ndb.Context.urlfetch = mock.create_autospec(
        ndb.Context.urlfetch,
        return_value=fut)

    with mock.patch('google.appengine.api.urlfetch'
                    '.fetch') as f:
      f.return_value = test_utils.MockUrlFetchResult(httplib.ACCEPTED,
                                                     None, None)
      self.assertEqual(httplib.ACCEPTED, api.do_request('foo')[0])

  def testNoRetryAfterDoRequestUrlFetchTimeout(self):
    retry_params = api_utils.RetryParams(max_retries=0)
    api = rest_api._RestApi('scope', retry_params=retry_params)

    fut = ndb.Future()
    fut.set_exception(urlfetch.DownloadError())
    ndb.Context.urlfetch = mock.create_autospec(
        ndb.Context.urlfetch,
        return_value=fut)
    self.assertRaises(urlfetch.DownloadError, api.do_request, 'foo')

  def testNoRetryAfterDoRequestResponseTimeout(self):
    retry_params = api_utils.RetryParams(max_retries=0)
    api = rest_api._RestApi('scope', retry_params=retry_params)

    fut = ndb.Future()
    fut.set_result(test_utils.MockUrlFetchResult(httplib.REQUEST_TIMEOUT,
                                                 None, None))
    ndb.Context.urlfetch = mock.create_autospec(
        ndb.Context.urlfetch,
        return_value=fut)
    self.assertEqual(httplib.REQUEST_TIMEOUT, api.do_request('foo')[0])


if __name__ == '__main__':
  unittest.main()
