# Copyright 2012 Google Inc. All Rights Reserved.

"""Tests for cloudstorage_api.py."""

from __future__ import with_statement



import gzip
import hashlib
import math
import os
import time
import unittest

from google.appengine.ext import testbed

from google.appengine.ext.cloudstorage import stub_dispatcher

try:
  import cloudstorage
  from cloudstorage import cloudstorage_api
  from cloudstorage import errors
except ImportError:
  from google.appengine.ext import cloudstorage
  from google.appengine.ext.cloudstorage import cloudstorage_api
  from google.appengine.ext.cloudstorage import errors

BUCKET = '/bucket'
TESTFILE = BUCKET + '/testfile'
DEFAULT_CONTENT = ['a'*1024*257,
                   'b'*1024*257,
                   'c'*1024*257]


class CloudStorageTest(unittest.TestCase):
  """Test for cloudstorage."""

  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_app_identity_stub()
    self.testbed.init_blobstore_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_urlfetch_stub()
    self._old_max_keys = stub_dispatcher._MAX_GET_BUCKET_RESULT
    stub_dispatcher._MAX_GET_BUCKET_RESULT = 2
    self.start_time = time.time()
    cloudstorage.set_default_retry_params(None)

  def tearDown(self):
    stub_dispatcher._MAX_GET_BUCKET_RESULT = self._old_max_keys
    self.testbed.deactivate()

  def CreateFile(self, filename):
    f = cloudstorage.open(filename,
                          'w',
                          'text/plain',
                          {'x-goog-meta-foo': 'foo',
                           'x-goog-meta-bar': 'bar',
                           'x-goog-acl': 'public-read',
                           'cache-control': 'public, max-age=6000',
                           'content-disposition': 'attachment; filename=f.txt'})
    for content in DEFAULT_CONTENT:
      f.write(content)
    f.close()

  def testGzip(self):
    with cloudstorage.open(TESTFILE, 'w', 'text/plain',
                           {'content-encoding': 'gzip'}) as f:
      gz = gzip.GzipFile('', 'wb', 9, f)
      gz.write('a'*1024)
      gz.write('b'*1024)
      gz.close()

    stat = cloudstorage.stat(TESTFILE)
    self.assertEqual('text/plain', stat.content_type)
    self.assertEqual('gzip', stat.metadata['content-encoding'])
    self.assertTrue(stat.st_size < 1024*2)

    with cloudstorage.open(TESTFILE) as f:
      gz = gzip.GzipFile('', 'rb', 9, f)
      result = gz.read(10)
      self.assertEqual('a'*10, result)
      self.assertEqual('a'*1014 + 'b'*1024, gz.read())

  def testCopy2(self):
    with cloudstorage.open(TESTFILE, 'w',
                           'text/foo', {'x-goog-meta-foo': 'foo'}) as f:
      f.write('abcde')

    dst = TESTFILE + 'copy'
    self.assertRaises(cloudstorage.NotFoundError, cloudstorage.stat, dst)
    cloudstorage_api._copy2(TESTFILE, dst)

    src_stat = cloudstorage.stat(TESTFILE)
    dst_stat = cloudstorage.stat(dst)
    self.assertEqual(src_stat.st_size, dst_stat.st_size)
    self.assertEqual(src_stat.etag, dst_stat.etag)
    self.assertEqual(src_stat.content_type, dst_stat.content_type)
    self.assertEqual(src_stat.metadata, dst_stat.metadata)

    with cloudstorage.open(dst) as f:
      self.assertEqual('abcde', f.read())

    cloudstorage.delete(dst)
    cloudstorage.delete(TESTFILE)

  def testDelete(self):
    self.assertRaises(errors.NotFoundError, cloudstorage.delete, TESTFILE)
    self.CreateFile(TESTFILE)
    cloudstorage.delete(TESTFILE)
    self.assertRaises(errors.NotFoundError, cloudstorage.delete, TESTFILE)
    self.assertRaises(errors.NotFoundError, cloudstorage.stat, TESTFILE)

  def testReadEntireFile(self):
    f = cloudstorage.open(TESTFILE, 'w')
    f.write('abcde')
    f.close()

    f = cloudstorage.open(TESTFILE, read_buffer_size=1)
    self.assertEqual('abcde', f.read())
    f.close()

    f = cloudstorage.open(TESTFILE)
    self.assertEqual('abcde', f.read(8))
    f.close()

  def testReadNonexistFile(self):
    self.assertRaises(errors.NotFoundError, cloudstorage.open, TESTFILE)

  def testRetryParams(self):
    retry_params = cloudstorage.RetryParams(max_retries=0)
    cloudstorage.set_default_retry_params(retry_params)

    retry_params.max_retries = 1000
    with cloudstorage.open(TESTFILE, 'w') as f:
      self.assertEqual(0, f._api.retry_params.max_retries)

    with cloudstorage.open(TESTFILE, 'w') as f:
      cloudstorage.set_default_retry_params(retry_params)
      self.assertEqual(0, f._api.retry_params.max_retries)

    per_call_retry_params = cloudstorage.RetryParams()
    with cloudstorage.open(TESTFILE, 'w',
                           retry_params=per_call_retry_params) as f:
      self.assertEqual(per_call_retry_params, f._api.retry_params)

  def testReadEmptyFile(self):
    f = cloudstorage.open(TESTFILE, 'w')
    f.write('')
    f.close()

    f = cloudstorage.open(TESTFILE)
    self.assertEqual('', f.read())
    self.assertEqual('', f.read())
    f.close()

  def testReadSmall(self):
    f = cloudstorage.open(TESTFILE, 'w')
    f.write('abcdefghij')
    f.close()

    f = cloudstorage.open(TESTFILE, read_buffer_size=3)
    self.assertEqual('ab', f.read(2))
    self.assertEqual('c', f.read(1))
    self.assertEqual('de', f.read(2))
    self.assertEqual('fghij', f.read())
    f.close()

  def testWriteRead(self):
    f = cloudstorage.open(TESTFILE, 'w')
    f.write('a')
    f.write('b'*1024)
    f.write('c'*1024 + '\n')
    f.write('d'*1024*1024)
    f.write('e'*1024*1024*10)
    self.assertRaises(errors.NotFoundError, cloudstorage.stat, TESTFILE)
    f.close()

    f = cloudstorage.open(TESTFILE)
    self.assertEqual('a' + 'b'*1024, f.read(1025))
    self.assertEqual('c'*1024 + '\n', f.readline())
    self.assertEqual('d'*1024*1024, f.read(1024*1024))
    self.assertEqual('e'*1024*1024*10, f.read())
    self.assertEqual('', f.read())
    self.assertEqual('', f.readline())

  def WriteInBlockSizeTest(self):
    f = cloudstorage.open(TESTFILE, 'w')
    f.write('a'*256*1024)
    f.write('b'*256*1024)
    f.close()

    f = cloudstorage.open(TESTFILE)
    self.assertEqual('a'*256*1024 + 'b'*256*1024, f.read())
    self.assertEqual('', f.read())
    self.assertEqual('', f.readline())
    f.close()

  def testWriteReadWithContextManager(self):
    with cloudstorage.open(TESTFILE, 'w') as f:
      f.write('a')
      f.write('b'*1024)
      f.write('c'*1024 + '\n')
      f.write('d'*1024*1024)
      f.write('e'*1024*1024*10)
    self.assertTrue(f._closed)

    with cloudstorage.open(TESTFILE) as f:
      self.assertEqual('a' + 'b'*1024, f.read(1025))
      self.assertEqual('c'*1024 + '\n', f.readline())
      self.assertEqual('d'*1024*1024, f.read(1024*1024))
      self.assertEqual('e'*1024*1024*10, f.read())
      self.assertEqual('', f.read())
      self.assertEqual('', f.readline())
    self.assertTrue(f._closed)

  def testSeekAndTell(self):
    f = cloudstorage.open(TESTFILE, 'w')
    f.write('abcdefghij')
    f.close()

    f = cloudstorage.open(TESTFILE)
    f.seek(5)
    self.assertEqual(5, f.tell())
    self.assertEqual('f', f.read(1))
    self.assertEqual(6, f.tell())
    f.seek(-1, os.SEEK_CUR)
    self.assertEqual('f', f.read(1))
    f.seek(-1, os.SEEK_END)
    self.assertEqual('j', f.read(1))

  def testStat(self):
    self.CreateFile(TESTFILE)
    filestat = cloudstorage.stat(TESTFILE)
    content = ''.join(DEFAULT_CONTENT)
    self.assertEqual(len(content), filestat.st_size)
    self.assertEqual('text/plain', filestat.content_type)
    self.assertEqual('foo', filestat.metadata['x-goog-meta-foo'])
    self.assertEqual('bar', filestat.metadata['x-goog-meta-bar'])
    self.assertEqual('public, max-age=6000', filestat.metadata['cache-control'])
    self.assertEqual(
        'attachment; filename=f.txt',
        filestat.metadata['content-disposition'])
    self.assertEqual(TESTFILE, filestat.filename)
    self.assertEqual(hashlib.md5(content).hexdigest(), filestat.etag)
    self.assertTrue(math.floor(self.start_time) <= filestat.st_ctime)
    self.assertTrue(filestat.st_ctime <= time.time())

  def testListBucket(self):
    bars = [BUCKET + '/test/bar' + str(i) for i in range(3)]
    foos = [BUCKET + '/test/foo' + str(i) for i in range(3)]
    filenames = bars + foos
    for filename in filenames:
      self.CreateFile(filename)

    bucket = cloudstorage.listbucket(BUCKET, prefix='test/')
    self.assertEqual(filenames, [stat.filename for stat in bucket])

    bucket = cloudstorage.listbucket(BUCKET, prefix='test/', max_keys=1)
    stats = list(bucket)
    self.assertEqual(1, len(stats))
    stat = stats[0]
    content = ''.join(DEFAULT_CONTENT)
    self.assertEqual(filenames[0], stat.filename)
    self.assertEqual(len(content), stat.st_size)
    self.assertEqual(hashlib.md5(content).hexdigest(), stat.etag)

    bucket = cloudstorage.listbucket(BUCKET,
                                     prefix='test/',
                                     marker='test/foo0',
                                     max_keys=1)
    stats = [stat for stat in bucket]
    self.assertEqual(1, len(stats))
    stat = stats[0]
    self.assertEqual(foos[1], stat.filename)


if __name__ == '__main__':
  unittest.main()
