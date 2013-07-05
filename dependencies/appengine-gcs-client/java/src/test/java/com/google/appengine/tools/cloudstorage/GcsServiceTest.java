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

import com.google.appengine.tools.development.testing.LocalBlobstoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalDatastoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalFileServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalServiceTestHelper;
import com.google.appengine.tools.development.testing.LocalTaskQueueTestConfig;
import com.google.common.base.Charsets;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.util.Random;

/**
 * End to end test to test the basics of the GcsService. This class uses the in-process
 * implementation, but provides coverage for everything above the RawGcsService
 *
 */
@RunWith(JUnit4.class)
public class GcsServiceTest {

  private final LocalServiceTestHelper helper = new LocalServiceTestHelper(
      new LocalTaskQueueTestConfig(), new LocalFileServiceTestConfig(),
      new LocalBlobstoreServiceTestConfig(), new LocalDatastoreServiceTestConfig());

  @Before
  public void setUp() throws Exception {
    helper.setUp();
  }

  @After
  public void tearDown() throws Exception {
    helper.tearDown();
  }

  @Test
  public void testReadWrittenData() throws IOException {
    Charset utf8 = Charsets.UTF_8;
    String content = "FooBar";
    GcsFilename filename = new GcsFilename("testReadWrittenDataBucket", "testReadWrittenDataFile");

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());

    outputChannel.write(utf8.encode(CharBuffer.wrap(content)));
    outputChannel.close();

    GcsInputChannel readChannel = gcsService.openReadChannel(filename, 0);
    ByteBuffer result = ByteBuffer.allocate(7);
    int read = readChannel.read(result);
    result.limit(read);

    assertEquals(6, read);
    result.rewind();
    assertEquals(content, utf8.decode(result).toString());
    gcsService.delete(filename);
  }

  @Test
  public void testWrite10mb() throws IOException {
    byte[] content = new byte[10 * 1024 * 1024 + 1];
    Random r = new Random();
    r.nextBytes(content);
    GcsFilename filename = new GcsFilename("testWrite10mbBucket", "testWrite10mbFile");

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());

    outputChannel.write(ByteBuffer.wrap(content));
    outputChannel.close();

    GcsInputChannel readChannel = gcsService.openReadChannel(filename, 0);
    verifyContent(content, readChannel, 25000);
    gcsService.delete(filename);
  }

  @Test
  public void testShortFileLongBuffer() throws IOException {
    byte[] content = new byte[1024];
    Random r = new Random();
    r.nextBytes(content);
    GcsFilename filename =
        new GcsFilename("testShortFileLongBufferBucket", "testShortFileLongBufferFile");

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());

    outputChannel.write(ByteBuffer.wrap(content));
    outputChannel.close();

    GcsInputChannel readChannel = gcsService.openPrefetchingReadChannel(filename, 0, 512 * 1024);
    verifyContent(content, readChannel, 13);
    gcsService.delete(filename);
  }

  @Test
  public void testDelete() throws IOException {
    byte[] content = new byte[1024];
    Random r = new Random();
    r.nextBytes(content);
    GcsFilename filename = new GcsFilename("testDeleteBucket", "testDeleteFile");

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());

    outputChannel.write(ByteBuffer.wrap(content));
    outputChannel.close();

    gcsService.delete(filename);

    ByteBuffer result = ByteBuffer.allocate(1);

    GcsInputChannel readChannel = gcsService.openReadChannel(filename, 0);
    try {
      readChannel.read(result);
      fail();
    } catch (IOException e) {
    }

    readChannel = gcsService.openPrefetchingReadChannel(filename, 0, 512 * 1024);
    try {
      readChannel.read(result);
      fail();
    } catch (IOException e) {
    }
  }

  @Test
  public void testBufferedReads() throws IOException {
    byte[] content = new byte[1 * 1024 * 1024 + 1];
    Random r = new Random();
    r.nextBytes(content);
    GcsFilename filename = new GcsFilename("testBufferedReadsBucket", "testBufferedReadsFile");

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());

    outputChannel.write(ByteBuffer.wrap(content));
    outputChannel.close();

    GcsInputChannel readChannel = gcsService.openPrefetchingReadChannel(filename, 0, 512 * 1024);
    verifyContent(content, readChannel, 13);
    gcsService.delete(filename);
  }

  @Test
  public void testReadMetadata() throws IOException {
    byte[] content = new byte[1 * 1024 * 1024 + 1];
    Random r = new Random();
    r.nextBytes(content);
    GcsFilename filename = new GcsFilename("testReadMetadataBucket", "testReadMetadataFile");

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsFileOptions options = GcsFileOptions.getDefaultInstance();
    GcsOutputChannel outputChannel = gcsService.createOrReplace(filename, options);

    outputChannel.write(ByteBuffer.wrap(content));
    outputChannel.close();

    GcsFileMetadata metadata = gcsService.getMetadata(filename);
    assertNotNull(metadata);
    assertEquals(filename, metadata.getFilename());
    assertEquals(content.length, metadata.getLength());
    assertEquals(options, metadata.getOptions());
  }

  @Test
  public void testEmptyMetadata() throws IOException {
    GcsFilename filename = new GcsFilename("testEmptyMetadataBucket", "testEmptyMetadataFile");
    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsFileMetadata metadata = gcsService.getMetadata(filename);
    assertNull(metadata);
  }


  private void verifyContent(byte[] content, GcsInputChannel readChannel, int readSize)
      throws IOException {
    ByteBuffer result = ByteBuffer.allocate(readSize);
    ByteBuffer wrapped = ByteBuffer.wrap(content);
    int offset = 0;
    int read = readChannel.read(result);
    while (read != -1) {
      result.limit(read);
      wrapped.position(offset);
      offset += read;
      wrapped.limit(offset);

      assertTrue(read > 0);
      assertTrue(read <= readSize);

      result.rewind();
      assertEquals(wrapped, result);
      read = readChannel.read(result);
    }
  }


}
