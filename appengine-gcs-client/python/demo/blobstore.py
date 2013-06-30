# Copyright 2013 Google Inc. All Rights Reserved.


"""A sample app that operates on GCS files with blobstore API."""

from __future__ import with_statement

import cloudstorage as gcs
import main
import webapp2

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers


def CreateFile(filename):
  """Create a GCS file with GCS client lib.

  Args:
    filename: GCS filename.

  Returns:
    The corresponding string blobkey for this GCS file.
  """
  with gcs.open(filename, 'w') as f:
    f.write('abcde\n')

  blobstore_filename = '/gs' + filename
  return blobstore.create_gs_key(blobstore_filename)


class GCSHandler(webapp2.RequestHandler):

  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    gcs_filename = main.BUCKET + '/blobstore_demo'
    blob_key = CreateFile(gcs_filename)

    self.response.write('Fetched data %s\n' %
                        blobstore.fetch_data(blob_key, 0, 2))

    blobstore.delete(blob_key)


class GCSServingHandler(blobstore_handlers.BlobstoreDownloadHandler):

  def get(self):
    blob_key = CreateFile(main.BUCKET + '/blobstore_serving_demo')
    self.send_blob(blob_key)


app = webapp2.WSGIApplication([('/blobstore/ops', GCSHandler),
                               ('/blobstore/serve', GCSServingHandler)],
                              debug=True)
