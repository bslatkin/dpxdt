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

import static org.junit.Assert.*;

import com.google.appengine.tools.development.testing.LocalBlobstoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalDatastoreServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalFileServiceTestConfig;
import com.google.appengine.tools.development.testing.LocalServiceTestHelper;
import com.google.appengine.tools.development.testing.LocalTaskQueueTestConfig;
import com.google.common.base.Charsets;

import org.hamcrest.CoreMatchers;
import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.ErrorCollector;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;

/**
 * Test the InputChannels (reading from GCS)
 */
@RunWith(JUnit4.class)
public class GcsInputChannelTest {
  private final LocalServiceTestHelper helper = new LocalServiceTestHelper(
      new LocalTaskQueueTestConfig(), new LocalFileServiceTestConfig(),
      new LocalBlobstoreServiceTestConfig(), new LocalDatastoreServiceTestConfig());

  private enum ChannelType {
    SIMPLE_GCS_INPUT,
    PREFETCHING_GCS_INPUT
  }

  private enum TestFile {
    ZERO(new GcsFilename("unit-tests", "zeroFile"), 0),
    SMALL(new GcsFilename("unit-tests", "smallFile"), 100),
    LARGE(new GcsFilename("unit-tests", "largeFile"), 10000);

    public final GcsFilename filename;
    public final int contentSize;

    TestFile(GcsFilename filename, int contentSize) {
      this.filename = filename;
      this.contentSize = contentSize;
    }
  }

  @Before
  public void setUp() throws Exception {
    helper.setUp();

    Charset utf8 = Charsets.UTF_8;
    GcsService gcsService = GcsServiceFactory.createGcsService();
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
  public void readAfterEndOfFile() throws IOException {
    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsInputChannel readChannel = gcsService.openPrefetchingReadChannel(
        TestFile.SMALL.filename, TestFile.SMALL.contentSize, 1024);
    int result = readChannel.read(ByteBuffer.allocate(100));
    assertEquals(result, -1);
  }

  @Test
  public void readOneByteAtATime() throws IOException {
    GcsService gcsService = GcsServiceFactory.createGcsService();
    GcsInputChannel readChannel =
        gcsService.openPrefetchingReadChannel(TestFile.LARGE.filename, 0, 1024);
    ByteBuffer buff = ByteBuffer.allocate(1);
    for (int i = 0; i < TestFile.LARGE.contentSize; i++) {
      int result = readChannel.read(buff);
      assertEquals(result, 1);
      buff.clear();
    }
    int result = readChannel.read(buff);
    assertEquals(result, -1);
  }

  private GcsInputChannel createChannel(
      ChannelType type, GcsFilename filename, int offset, int fetchSize) throws IOException {
    final GcsService gcsService = GcsServiceFactory.createGcsService();
    switch (type) {
      case SIMPLE_GCS_INPUT:
        return gcsService.openReadChannel(filename, offset);
      case PREFETCHING_GCS_INPUT:
        return gcsService.openPrefetchingReadChannel(filename, offset, fetchSize);
      default:
        throw new RuntimeException("Unsupported Channel Type: " + type.toString());
    }
  }

  private String runTest(GcsInputChannel channel, int readSize) throws IOException {
    final StringBuffer contents = new StringBuffer();
    try {
      final ByteBuffer buffer = ByteBuffer.allocateDirect(readSize);
      int read = 0;
      final CharsetDecoder decoder = Charsets.UTF_8.newDecoder();
      while (read >= 0) {
        read = channel.read(buffer);
        buffer.flip();
        contents.append(decoder.decode(buffer));
        buffer.rewind();
        buffer.limit(buffer.capacity());
      }
    } finally {
      channel.close();
    }
    return contents.toString();
  }

  @Rule
  public ErrorCollector collector = new ErrorCollector();

  @Test
  public void runAllTests() throws IOException {
    double[] fetchMultipliers = {1.2, 1.0, 0.7, 0.5, 0.25, 0.4};

    double[] readMultipliers = {1.4, 2.0, 1.0, 0.5, 0.3};

    int[] offsets = {Integer.MIN_VALUE, Integer.MAX_VALUE, -5, -1, 0, 1, 5};

    int testNum = 0;
    for (ChannelType type : ChannelType.values()) {
      for (TestFile file : TestFile.values()) {
        for (double fetchMultiplier : fetchMultipliers) {
          for (double readMultiplier : readMultipliers) {
            for (int offset : offsets) {
              testNum++;

              int fetchSize = (int) (file.contentSize * fetchMultiplier);
              int readSize = (int) (file.contentSize * readMultiplier);
              int finalOffset = 0;
              if (offset == Integer.MIN_VALUE) {
                finalOffset = 0;
              } else if (offset == Integer.MAX_VALUE) {
                finalOffset = 1;
              } else {
                finalOffset = file.contentSize + offset;
              }

              String testName = "Test [" + testNum + "] Fetching: " + file.filename + " w/ size="
                  + file.contentSize + " using: " + type + " w/ fetch=" + fetchSize + ", read="
                  + readSize + ", offset=" + finalOffset;

              GcsInputChannel channel = null;
              boolean shouldCreate =
                  (type != ChannelType.PREFETCHING_GCS_INPUT || (fetchSize >= 1024))
                  && finalOffset >= 0;
              try {
                channel = createChannel(type, file.filename, finalOffset, fetchSize);
                collector.checkThat(
                    "Should have failed due to bad fetch size  or illegal offset on " + testName,
                    shouldCreate, CoreMatchers.is(true));
              } catch (IllegalArgumentException exception) {
                collector.checkThat("Should not have failed due to bad fetch size on " + testName
                    + " w/" + exception.getClass().getName() + " " + exception.getMessage(),
                    !shouldCreate, CoreMatchers.is(true));
                continue;
              }

              String contents = null;
              boolean shouldRun = (readSize > 0);
              try {
                contents = runTest(channel, readSize);
                collector.checkThat("Should have failed due to bad offset/read size " + testName,
                    shouldRun, CoreMatchers.is(true));
              } catch (Exception exception) {
                collector.checkThat("Should not have failed due to bad offset " + testName + " w/"
                    + exception.getClass().getName() + " " + exception.getMessage(), !shouldRun,
                    CoreMatchers.is(true));
                continue;
              }

              collector.checkThat("Sizes should have matched " + testName, contents.length(),
                  CoreMatchers.is(Math.max(0, file.contentSize - finalOffset)));
            }
          }
        }
      }
    }
  }
}
