# Copyright 2012 Google Inc. All Rights Reserved.

"""File Interface for Google Cloud Storage."""



from __future__ import with_statement



__all__ = ['delete',
           'listbucket',
           'open',
           'stat',
          ]

import urllib
import xml.etree.ElementTree as ET
from . import common
from . import errors
from . import storage_api


def open(filename,
         mode='r',
         content_type=None,
         options=None,
         read_buffer_size=storage_api.ReadBuffer.DEFAULT_BUFFER_SIZE,
         retry_params=None,
         _account_id=None):
  """Opens a Google Cloud Storage file and returns it as a File-like object.

  Args:
    filename: A Google Cloud Storage filename of form '/bucket/filename'.
    mode: 'r' for reading mode. 'w' for writing mode.
      In reading mode, the file must exist. In writing mode, a file will
      be created or be overrode.
    content_type: The MIME type of the file. str. Only valid in writing mode.
    options: A str->basestring dict to specify additional headers to pass to
      GCS e.g. {'x-goog-acl': 'private', 'x-goog-meta-foo': 'foo'}.
      Supported options are x-goog-acl, x-goog-meta-, cache-control,
      content-disposition, and content-encoding.
      Only valid in writing mode.
      See https://developers.google.com/storage/docs/reference-headers
      for details.
    read_buffer_size: The buffer size for read. If buffer is empty, the read
      stream will asynchronously prefetch a new buffer before the next read().
      To minimize blocking for large files, always read in buffer size.
      To minimize number of requests for small files, set a larger
      buffer size.
    retry_params: An instance of api_utils.RetryParams for subsequent calls
      to GCS from this file handle. If None, the default one is used.
    _account_id: Internal-use only.

  Returns:
    A reading or writing buffer that supports File-like interface. Buffer
    must be closed after operations are done.

  Raises:
    errors.AuthorizationError: if authorization failed.
    errors.NotFoundError: if an object that's expected to exist doesn't.
    ValueError: invalid open mode or if content_type or options are specified
      in reading mode.
  """
  common.validate_file_path(filename)
  api = _get_storage_api(retry_params=retry_params, account_id=_account_id)

  if mode == 'w':
    common.validate_options(options)
    return storage_api.StreamingBuffer(api, filename, content_type, options)
  elif mode == 'r':
    if content_type or options:
      raise ValueError('Options and content_type can only be specified '
                       'for writing mode.')
    return storage_api.ReadBuffer(api,
                                  filename,
                                  max_buffer_size=read_buffer_size)
  else:
    raise ValueError('Invalid mode %s.' % mode)


def delete(filename, retry_params=None, _account_id=None):
  """Delete a Google Cloud Storage file.

  Args:
    filename: A Google Cloud Storage filename of form '/bucket/filename'.
    retry_params: An api_utils.RetryParams for this call to GCS. If None,
      the default one is used.
    _account_id: Internal-use only.

  Raises:
    errors.NotFoundError: if the file doesn't exist prior to deletion.
  """
  api = _get_storage_api(retry_params=retry_params, account_id=_account_id)
  common.validate_file_path(filename)
  status, _, _ = api.delete_object(filename)
  errors.check_status(status, [204])


def stat(filename, retry_params=None, _account_id=None):
  """Get GCSFileStat of a Google Cloud storage file.

  Args:
    filename: A Google Cloud Storage filename of form '/bucket/filename'.
    retry_params: An api_utils.RetryParams for this call to GCS. If None,
      the default one is used.
    _account_id: Internal-use only.

  Returns:
    a GCSFileStat object containing info about this file.

  Raises:
    errors.AuthorizationError: if authorization failed.
    errors.NotFoundError: if an object that's expected to exist doesn't.
  """
  common.validate_file_path(filename)
  api = _get_storage_api(retry_params=retry_params, account_id=_account_id)
  status, headers, _ = api.head_object(filename)
  errors.check_status(status, [200])
  file_stat = common.GCSFileStat(
      filename=filename,
      st_size=headers.get('content-length'),
      st_ctime=common.http_time_to_posix(headers.get('last-modified')),
      etag=headers.get('etag'),
      content_type=headers.get('content-type'),
      metadata=common.get_metadata(headers))

  return file_stat


def _copy2(src, dst, retry_params=None):
  """Copy the file content and metadata from src to dst.

  Internal use only!

  Args:
    src: /bucket/filename
    dst: /bucket/filename
    retry_params: An api_utils.RetryParams for this call to GCS. If None,
      the default one is used.

  Raises:
    errors.AuthorizationError: if authorization failed.
    errors.NotFoundError: if an object that's expected to exist doesn't.
  """
  common.validate_file_path(src)
  common.validate_file_path(dst)
  if src == dst:
    return

  api = _get_storage_api(retry_params=retry_params)
  status, headers, _ = api.put_object(
      dst,
      headers={'x-goog-copy-source': src,
               'Content-Length': '0'})
  errors.check_status(status, [200], headers)


def listbucket(bucket, marker=None, prefix=None, max_keys=None,
               retry_params=None, _account_id=None):
  """Return an GCSFileStat iterator over files in the given bucket.

  Optional arguments are to limit the result to a subset of files under bucket.

  This function is asynchronous. It does not block unless iterator is called
  before the iterator gets result.

  Args:
    bucket: A Google Cloud Storage bucket of form "/bucket".
    marker: A string after which (exclusive) to start listing.
    prefix: Limits the returned filenames to those with this prefix. no regex.
    max_keys: The maximum number of filenames to match. int.
    retry_params: An api_utils.RetryParams for this call to GCS. If None,
      the default one is used.
    _account_id: Internal-use only.

  Example:
    For files "/bucket/foo1", "/bucket/foo2", "/bucket/foo3", "/bucket/www",
    listbucket("/bucket", prefix="foo", marker="foo1")
    will match "/bucket/foo2" and "/bucket/foo3".

    See Google Cloud Storage documentation for more details and examples.
    https://developers.google.com/storage/docs/reference-methods#getbucket

  Returns:
    An GSFileStat iterator over matched files, sorted by filename.
    Only filename, etag, and st_size are set in these GSFileStat objects.
  """
  common.validate_bucket_path(bucket)
  api = _get_storage_api(retry_params=retry_params, account_id=_account_id)
  options = {}
  if marker:
    options['marker'] = marker
  if max_keys:
    options['max-keys'] = max_keys
  if prefix:
    options['prefix'] = prefix

  return _Bucket(api, bucket, options)


class _Bucket(object):
  """A wrapper for a GCS bucket as the return value of listbucket."""

  def __init__(self, api, path, options):
    """Initialize.

    Args:
      api: storage_api instance.
      path: bucket path of form '/bucket'.
      options: a dict of listbucket options. Please see listbucket doc.
    """
    self._api = api
    self._path = path
    self._options = options.copy()
    self._get_bucket_fut = self._api.get_bucket_async(
        self._path + '?' + urllib.urlencode(self._options))

  def _add_ns(self, tagname):
    return '{%(ns)s}%(tag)s' % {'ns': common.CS_XML_NS,
                                'tag': tagname}

  def __iter__(self):
    """Iter over the bucket.

    Yields:
      GCSFileStat: a GCSFileStat for an object in the bucket.
        They are ordered by GCSFileStat.filename.
    """
    total = 0
    while self._get_bucket_fut:
      status, _, content = self._get_bucket_fut.get_result()
      errors.check_status(status, [200])
      root = ET.fromstring(content)
      for contents in root.getiterator(self._add_ns('Contents')):
        last_modified = contents.find(self._add_ns('LastModified')).text
        st_ctime = common.dt_str_to_posix(last_modified)
        yield common.GCSFileStat(
            self._path + '/' + contents.find(self._add_ns('Key')).text,
            contents.find(self._add_ns('Size')).text,
            contents.find(self._add_ns('ETag')).text,
            st_ctime)
        total += 1

      max_keys = root.find(self._add_ns('MaxKeys'))
      next_marker = root.find(self._add_ns('NextMarker'))
      if (max_keys is None or total < int(max_keys.text)) and (
          next_marker is not None):
        self._options['marker'] = next_marker.text
        self._get_bucket_fut = self._api.get_bucket_async(
            self._path + '?' + urllib.urlencode(self._options))
      else:
        self._get_bucket_fut = None


def _get_storage_api(retry_params, account_id=None):
  """Returns storage_api instance for API methods.

  Args:
    retry_params: An instance of api_utils.RetryParams.
    account_id: Internal-use only.

  Returns:
    A storage_api instance to handle urlfetch work to GCS.
    On dev appserver, this instance by default will talk to a local stub
    unless common.ACCESS_TOKEN is set. That token will be used to talk
    to the real GCS.
  """


  api = storage_api._StorageApi(storage_api._StorageApi.full_control_scope,
                                service_account_id=account_id,
                                retry_params=retry_params)
  if common.local_run() and not common.get_access_token():
    api.api_url = 'http://' + common.LOCAL_API_HOST
  if common.get_access_token():
    api.token = common.get_access_token()
  return api
