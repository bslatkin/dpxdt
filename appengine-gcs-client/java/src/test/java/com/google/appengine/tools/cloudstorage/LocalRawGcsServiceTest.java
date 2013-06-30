/*
 * Copyright 2012 Google Inc. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.google.appengine.tools.cloudstorage;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import com.google.appengine.tools.cloudstorage.dev.LocalRawGcsServiceFactory;
import com.google.appengine.tools.development.testing.LocalBlobstoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalDatastoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalFileServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalServiceTestHelper;
import com.google.appengine.tools.development.testing.LocalTaskQueueTestConfig;
import com.google.common.base.Charsets;

import junit.framework.Assert;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.util.concurrent.ExecutionException;

/**
 * Verify the LocalRawGcsService responds like the production version
 */
@RunWith(JUnit4.class)
public class LocalRawGcsServiceTest {
  private final LocalServiceTestHelper helper = new LocalServiceTestHelper(
      new LocalTaskQueueTestConfig(), new LocalFileServiceTestConfig(),
      new LocalBlobstoreServiceTestConfig(), new LocalDatastoreServiceTestConfig());
  private RawGcsService rawGcsService;

  private enum TestFile {
    SMALL(new GcsFilename("unit-tests", "smallFile"), 100);

    public final GcsFilename filename;
    public final int contentSize;

    TestFile(GcsFilename filename, int contentSize) {
      this.filename = filename;
      this.contentSize = contentSize;
    }
  }

  @Before
  public void setup() throws IOException {
    helper.setUp();

    rawGcsService = LocalRawGcsServiceFactory.createLocalRawGcsService();
    GcsService gcsService = new GcsServiceImpl(rawGcsService, RetryParams.getDefaultInstance());

    Charset utf8 = Charsets.UTF_8;
    for (TestFile file : TestFile.values()) {
      StringBuffer contents = new StringBuffer(file.contentSize);
      for (int i = 0; i < file.contentSize; i++) {
        contents.append(i % 10);
      }
      GcsOutputChannel outputChannel =
          gcsService.createOrReplace(file.filename, GcsFileOptions.getDefaultInstance());
      outputChannel.write(utf8.encode(CharBuffer.wrap(contents.toString())));
      outputChannel.close();
    }
  }

  @After
  public void tearDown() throws Exception {
    helper.tearDown();
  }

  @Test
  public void testDeleteExistingFile() throws IOException, InterruptedException {
    GcsFilename filename = new GcsFilename("unit-tests", "testDelete");
    GcsService gcsService = new GcsServiceImpl(rawGcsService, RetryParams.getDefaultInstance());
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());
    outputChannel.write(ByteBuffer.wrap(new byte[] {0, 1, 2, 3, 4}));
    outputChannel.close();
    GcsFileMetadata metadata = rawGcsService.getObjectMetadata(filename, 1000);
    assertNotNull(metadata);
    assertEquals(5, metadata.getLength());
    boolean deleted = rawGcsService.deleteObject(filename, 1000);
    assertTrue(deleted);
    metadata = rawGcsService.getObjectMetadata(filename, 1000);
    assertNull(metadata);
    ByteBuffer dst = ByteBuffer.allocate(200);
    try {
      rawGcsService.readObjectAsync(dst, filename, 0, 1000).get();
      fail();
    } catch (ExecutionException e) {
      assertEquals(FileNotFoundException.class, e.getCause().getClass());
    }
  }

  @Test(expected = IllegalArgumentException.class)
  public void testReadObjectAsyncNegativeOffset() {
    ByteBuffer tmpBuffer = ByteBuffer.allocate(200);
    rawGcsService.readObjectAsync(tmpBuffer, TestFile.SMALL.filename, -100, 1000);
  }

  @Test
  public void testReadObjectAsyncZeroOffset() throws InterruptedException, ExecutionException {
    ByteBuffer tmpBuffer = ByteBuffer.allocate(100);
    rawGcsService.readObjectAsync(tmpBuffer, TestFile.SMALL.filename, 0, 1000).get();
    Assert.assertEquals(100, tmpBuffer.position());
  }

  @Test
  public void testReadObjectAsyncMidwayOffset() throws InterruptedException, ExecutionException {
    ByteBuffer tmpBuffer = ByteBuffer.allocate(100);
    rawGcsService.readObjectAsync(tmpBuffer, TestFile.SMALL.filename, 50, 1000).get();
    Assert.assertEquals(50, tmpBuffer.position());
  }

  @Test(expected = ExecutionException.class)
  public void testReadObjectAsyncEndOffset() throws InterruptedException, ExecutionException {
    ByteBuffer tmpBuffer = ByteBuffer.allocate(100);
    rawGcsService.readObjectAsync(tmpBuffer, TestFile.SMALL.filename, 100, 1000).get();
  }

  @Test(expected = ExecutionException.class)
  public void testReadObjectAsyncAfterEndOffset() throws InterruptedException, ExecutionException {
    ByteBuffer tmpBuffer = ByteBuffer.allocate(100);
    rawGcsService.readObjectAsync(tmpBuffer, TestFile.SMALL.filename, 200, 1000).get();
  }
}
