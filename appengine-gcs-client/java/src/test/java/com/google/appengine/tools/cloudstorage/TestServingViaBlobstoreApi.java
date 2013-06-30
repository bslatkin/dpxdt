package com.google.appengine.tools.cloudstorage;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertTrue;

import com.google.appengine.api.blobstore.BlobKey;
import com.google.appengine.api.blobstore.BlobstoreService;
import com.google.appengine.api.blobstore.BlobstoreServiceFactory;
import com.google.appengine.api.images.ImagesService;
import com.google.appengine.api.images.ImagesServiceFactory;
import com.google.appengine.api.images.ServingUrlOptions;
import com.google.appengine.tools.development.testing.LocalBlobstoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalDatastoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalImagesServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalServiceTestHelper;
import com.google.common.io.BaseEncoding;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import java.io.IOException;
import java.nio.ByteBuffer;

/**
 */
@RunWith(JUnit4.class)
public class TestServingViaBlobstoreApi {

  private static final GcsService GCS_SERVICE = GcsServiceFactory.createGcsService();
  private static final BlobstoreService BLOB_STORE = BlobstoreServiceFactory.getBlobstoreService();
  private static final ImagesService IMAGES_SERVICE = ImagesServiceFactory.getImagesService();

  private static final String PNG =
      "iVBORw0KGgoAAAANSUhEUgAAAsAAAAGMAQMAAADuk4YmAAAAA1BMVEX///+nxBvIAAAAAXRSTlMA"
      + "QObYZgAAADlJREFUeF7twDEBAAAAwiD7p7bGDlgYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
      + "AAAAAAAAwAGJrAABgPqdWQAAAABJRU5ErkJggg==";

  LocalServiceTestHelper helper = new LocalServiceTestHelper(
      new LocalBlobstoreServiceTestConfig(), new LocalDatastoreServiceTestConfig(),
      new LocalImagesServiceTestConfig());

  @Before
  public void setUp() throws Exception {
    helper.setUp();
  }

  @After
  public void tearDown() throws Exception {
    helper.tearDown();
  }

  @Test
  public void testFoundUrl() throws IOException {
    GcsFilename gcsFilename =
        new GcsFilename(TestServingViaBlobstoreApi.class.getName(), "testFoundUrl");
    GcsOutputChannel channel = GCS_SERVICE.createOrReplace(
        gcsFilename, new GcsFileOptions.Builder().mimeType("image/png").build());
    byte[] bytes = BaseEncoding.base64().decode(PNG);
    channel.write(ByteBuffer.wrap(bytes));
    channel.close();

    BlobKey blobKey = BLOB_STORE.createGsBlobKey(
        "/gs/" + gcsFilename.getBucketName() + "/" + gcsFilename.getObjectName());

    byte[] imageData = BLOB_STORE.fetchData(blobKey, 0, bytes.length);
    assertArrayEquals(bytes, imageData);

    ServingUrlOptions opts = ServingUrlOptions.Builder.withBlobKey(blobKey);
    opts.imageSize(bytes.length);
    String url = IMAGES_SERVICE.getServingUrl(opts);
    assertTrue(url.length() > 0);
  }
}
