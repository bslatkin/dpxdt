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
import static org.junit.Assert.assertTrue;

import com.google.appengine.tools.development.testing.LocalBlobstoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalDatastoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalFileServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalServiceTestHelper;
import com.google.appengine.tools.development.testing.LocalTaskQueueTestConfig;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.nio.ByteBuffer;
import java.util.Random;

/**
 * Test the OutputChannels (writing to GCS)
 */
@RunWith(JUnit4.class)
public class GcsOutputChannelTest {
  private static final int BUFFER_SIZE = 2 * 1024 * 1024;
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

  /**
   * Writes a file with the content supplied by pattern repeated over and over until the desired
   * size is reached. After each write call reconstruct is called the output channel.
   *
   *  We don't want to call close on the output channel while writing because this will prevent
   * additional writes. Similarly we don't put the close in a finally block, because we don't want
   * the partly written data to be used in the event of an exception.
   */
  @SuppressWarnings("resource")
  public void writeFile(String name, int size, byte[] pattern)
      throws IOException, ClassNotFoundException {
    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsFilename filename = new GcsFilename("GcsOutputChannelTestBucket", name);
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());
    outputChannel = reconstruct(outputChannel);
    for (int written = 0; written < size; written += pattern.length) {
      int toWrite = Math.min(pattern.length, size - written);
      outputChannel.write(ByteBuffer.wrap(pattern, 0, toWrite));
      outputChannel.waitForOutstandingWrites();
      outputChannel = reconstruct(outputChannel);
    }
    outputChannel.close();
  }

  /**
   * Read the file and verify it contains the expected pattern the expected number of times.
   */
  private void verifyContent(String name, byte[] content, int expectedSize) throws IOException {
    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsFilename filename = new GcsFilename("GcsOutputChannelTestBucket", name);
    GcsInputChannel readChannel = gcsService.openPrefetchingReadChannel(filename, 0, BUFFER_SIZE);
    ByteBuffer result = ByteBuffer.allocate(content.length);
    ByteBuffer wrapped = ByteBuffer.wrap(content);
    int size = 0;
    int read = readFully(readChannel, result);
    while (read != -1) {
      assertTrue(read > 0);
      size += read;
      result.rewind();
      result.limit(read);
      wrapped.limit(read);
      if (!wrapped.equals(result)) {
        assertEquals(wrapped, result);
      }
      read = readFully(readChannel, result);
    }
    assertEquals(expectedSize, size);
  }

  private int readFully(GcsInputChannel readChannel, ByteBuffer result) throws IOException {
    int totalRead = 0;
    while (result.hasRemaining()) {
      int read = readChannel.read(result);
      if (read == -1) {
        if (totalRead == 0) {
          totalRead = -1;
        }
        break;
      } else {
        totalRead += read;
      }
    }
    return totalRead;
  }

  /**
   * Serializes and deserializes the the GcsOutputChannel. This simulates the writing of the file
   * continuing from a different request.
   */
  private GcsOutputChannel reconstruct(GcsOutputChannel writeChannel)
      throws IOException, ClassNotFoundException {
    ByteArrayOutputStream bout = writeChannelToStream(writeChannel);
    ObjectInputStream in = new ObjectInputStream(new ByteArrayInputStream(bout.toByteArray()));
    return (GcsOutputChannel) in.readObject();
  }

  ByteArrayOutputStream writeChannelToStream(GcsOutputChannel outputChannel) throws IOException {
    ByteArrayOutputStream bout = new ByteArrayOutputStream();
    ObjectOutputStream oout = new ObjectOutputStream(bout);
    try {
      oout.writeObject(outputChannel);
    } finally {
      oout.close();
    }
    return bout;
  }


  @Test
  public void testSingleLargeWrite() throws IOException, ClassNotFoundException {
    int size = 5 * BUFFER_SIZE;
    byte[] content = new byte[size];
    Random r = new Random();
    r.nextBytes(content);
    writeFile("SingleLargeWrite", size, content);
    verifyContent("SingleLargeWrite", content, size);
  }

  @Test
  public void testSmallWrites() throws IOException, ClassNotFoundException {
    byte[] content = new byte[100];
    Random r = new Random();
    r.nextBytes(content);
    int size = 27 * 1024;
    assertTrue(size < BUFFER_SIZE);
    writeFile("testSmallWrites", size, content);
    verifyContent("testSmallWrites", content, size);
  }

  /**
   * Tests writing in multiple segments that is > RawGcsService.getChunkSizeBytes() but less than
   * the buffer size in {@link GcsOutputChannelImpl}.
   */
  @Test
  public void testLargeWrites() throws IOException, ClassNotFoundException {
    byte[] content = new byte[(int) (BUFFER_SIZE * 0.477)];
    Random r = new Random();
    r.nextBytes(content);
    int size = (int) (2.5 * BUFFER_SIZE);
    writeFile("testLargeWrites", size, content);
    verifyContent("testLargeWrites", content, size);
  }

  @Test
  public void testUnalignedWrites() throws IOException, ClassNotFoundException {
    byte[] content = new byte[997];
    Random r = new Random();
    r.nextBytes(content);
    int size = 2377 * 1033;
    assertTrue(size > BUFFER_SIZE);
    writeFile("testUnalignedWrites", size, content);
    verifyContent("testUnalignedWrites", content, size);
  }

  @Test
  public void testAlignedWrites() throws IOException, ClassNotFoundException {
    byte[] content = new byte[BUFFER_SIZE];
    Random r = new Random();
    r.nextBytes(content);
    writeFile("testUnalignedWrites", 5 * BUFFER_SIZE, content);
    verifyContent("testUnalignedWrites", content, 5 * BUFFER_SIZE);
  }

  @Test
  public void testPartialFlush() throws IOException {
    byte[] content = new byte[BUFFER_SIZE - 1];
    Random r = new Random();
    r.nextBytes(content);

    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsFilename filename = new GcsFilename("GcsOutputChannelTestBucket", "testPartialFlush");
    GcsOutputChannel outputChannel =
        gcsService.createOrReplace(filename, GcsFileOptions.getDefaultInstance());

    outputChannel.write(ByteBuffer.wrap(content, 0, content.length));

    ByteArrayOutputStream bout = writeChannelToStream(outputChannel);
    assertTrue(bout.size() >= BUFFER_SIZE);

    outputChannel.waitForOutstandingWrites();

    bout = writeChannelToStream(outputChannel);
    assertTrue(bout.size() < BUFFER_SIZE);
    assertTrue(bout.size() > 0);

    outputChannel.close();

    verifyContent("testPartialFlush", content, BUFFER_SIZE - 1);
  }


  /**
   * The other tests in this file assume a buffer size of 2mb. If this is changed this test will
   * fail. Before fixing it update the other tests.
   */
  @Test
  public void testBufferSize() {
    RawGcsService rawService = GcsServiceFactory.createRawGcsService();
    int bufferSize = GcsOutputChannelImpl.getBufferSize(rawService.getChunkSizeBytes());
    assertEquals(BUFFER_SIZE, bufferSize);
  }
}
