# Copyright 2012 Google Inc. All Rights Reserved.


"""A sample app that uses GCS client to operate on bucket and file."""

import os
import cloudstorage as gcs
import webapp2

my_default_retry_params = gcs.RetryParams(initial_delay=0.2,
                                          max_delay=5.0,
                                          backoff_factor=2,
                                          max_retry_period=15)
gcs.set_default_retry_params(my_default_retry_params)

BUCKET = '/yey-cloud-storage-trial'


class MainPage(webapp2.RequestHandler):

  def get(self):
    filename = BUCKET + '/demo-testfile'

    self.response.headers['Content-Type'] = 'text/plain'
    self.tmp_filenames_to_clean_up = []

    self.create_file(filename)
    self.response.write('\n\n')

    self.read_file(filename)
    self.response.write('\n\n')

    self.stat_file(filename)
    self.response.write('\n\n')

    self.list_bucket(BUCKET)
    self.response.write('\n\n')

    self.delete_files()

  def create_file(self, filename):
    """Create a file.

    The retry_params specified in the open call will override the default
    retry params for this particular file handle.

    Args:
      filename: filename.
    """
    self.response.write('Creating file %s\n' % filename)

    write_retry_params = gcs.RetryParams(backoff_factor=1.1)
    gcs_file = gcs.open(filename,
                        'w',
                        content_type='text/plain',
                        options={'x-goog-meta-foo': 'foo',
                                 'x-goog-meta-bar': 'bar'},
                        retry_params=write_retry_params)
    gcs_file.write('abcde\n')
    gcs_file.write('f'*1024*1024 + '\n')
    gcs_file.close()
    self.tmp_filenames_to_clean_up.append(filename)

  def read_file(self, filename):
    self.response.write('Truncated file content:\n')

    gcs_file = gcs.open(filename)
    self.response.write(gcs_file.readline())
    gcs_file.seek(-1024, os.SEEK_END)
    self.response.write(gcs_file.read())
    gcs_file.close()

  def stat_file(self, filename):
    self.response.write('File stat:\n')

    stat = gcs.stat(filename)
    self.response.write(repr(stat))

  def list_bucket(self, bucket):
    """Create several files and paginate through them.

    Production apps should set page_size to a practical value.

    Args:
      bucket: bucket.
    """
    self.response.write('Creating more files for listbucket...\n')
    self.create_file(bucket + '/foo1')
    self.create_file(bucket + '/foo2')
    self.response.write('\nListbucket result:\n')

    page_size = 1
    stats = gcs.listbucket(bucket, max_keys=page_size)
    while True:
      count = 0
      for stat in stats:
        count += 1
        self.response.write(repr(stat))
        self.response.write('\n')

      if count != page_size or count == 0:
        break
      last_filename = stat.filename[len(bucket)+1:]
      stats = gcs.listbucket(bucket, max_keys=page_size, marker=last_filename)

  def delete_files(self):
    self.response.write('Deleting files...\n')
    for filename in self.tmp_filenames_to_clean_up:
      try:
        gcs.delete(filename)
      except gcs.NotFoundError:
        pass


app = webapp2.WSGIApplication([('/', MainPage)],
                              debug=True)
