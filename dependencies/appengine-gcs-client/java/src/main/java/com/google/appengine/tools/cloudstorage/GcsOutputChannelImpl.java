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

import static com.google.common.base.Preconditions.checkNotNull;

import com.google.appengine.tools.cloudstorage.RawGcsService.RawGcsCreationToken;
import com.google.appengine.tools.cloudstorage.RetryHelper.Body;
import com.google.common.annotations.VisibleForTesting;
import com.google.common.base.Preconditions;

import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.ClosedChannelException;
import java.util.logging.Logger;

final class GcsOutputChannelImpl implements GcsOutputChannel, Serializable {

  private static final long serialVersionUID = 3011935384698648440L;

  @SuppressWarnings("unused")
  private static final Logger log = Logger.getLogger(GcsOutputChannelImpl.class.getName());

  private transient Object lock = new Object();
  private transient ByteBuffer buf;
  private transient RawGcsService raw;private RawGcsCreationToken token;
  private final GcsFilename filename;
  private RetryParams retryParams;


  GcsOutputChannelImpl(RawGcsService raw, RawGcsCreationToken nextToken, RetryParams retryParams) {
    this.retryParams = retryParams;
    this.raw = checkNotNull(raw, "Null raw");
    this.buf = ByteBuffer.allocate(getBufferSize(raw.getChunkSizeBytes()));
    this.token = checkNotNull(nextToken, "Null token");
    this.filename = nextToken.getFilename();
  }

  private void readObject(ObjectInputStream aInputStream)
      throws ClassNotFoundException, IOException {
    aInputStream.defaultReadObject();
    lock = new Object();
    raw = GcsServiceFactory.createRawGcsService();
    buf = ByteBuffer.allocate(getBufferSize(raw.getChunkSizeBytes()));
    int length = aInputStream.readInt();
    if (length > buf.capacity()) {
      throw new IllegalArgumentException(
          "Size of buffer is smaller than initial contents: " + length);
    }
    if (length > 0) {
      byte[] initialBuffer = new byte[length];
      for (int pos = 0; pos < length;) {
        pos += aInputStream.read(initialBuffer, pos, length - pos);
      }
      buf.put(initialBuffer);
    }
  }

  private void writeObject(ObjectOutputStream aOutputStream) throws IOException {
    aOutputStream.defaultWriteObject();
    int length = buf.position();
    aOutputStream.writeInt(length);
    if (length > 0) {
      buf.rewind();
      byte[] toWrite = new byte[length];
      buf.get(toWrite);
      aOutputStream.write(toWrite);
    }
  }

  @VisibleForTesting
  static int getBufferSize(int chunkSize) {
    if (chunkSize <= 256 * 1024) {
      return 8 * chunkSize;
    } else if (chunkSize <= 1024 * 1024) {
      return 2 * chunkSize;
    } else {
      return chunkSize;
    }
  }

  @Override
  public int getBufferSizeBytes() {
    return buf.capacity();
  }

  @Override
  public String toString() {
    return "GcsOutputChannelImpl [token=" + token + ", filename=" + filename
        + ", retryParams=" + retryParams + "]";
  }

  @Override
  public boolean isOpen() {
    synchronized (lock) {
      return token != null;
    }
  }

  @Override
  public GcsFilename getFilename() {
    return filename;
  }

  private ByteBuffer getSliceForWrite() {
    int oldPos = buf.position();
    buf.flip();
    ByteBuffer out = buf.slice();
    buf.limit(buf.capacity());
    buf.position(oldPos);

    return out;
  }

  @Override
  public void close() throws IOException {
    synchronized (lock) {
      if (!isOpen()) {
        return;
      }
      final ByteBuffer out = getSliceForWrite();
      RetryHelper.runWithRetries(new Body<Void>() {
        @Override
        public Void run() throws IOException {
          raw.finishObjectCreation(token, out, retryParams.getRequestTimeoutMillis());
          return null;
        }
      }, retryParams);
      token = null;
    }
  }

  private void flushIfNeeded() throws IOException {
    if (!buf.hasRemaining()) {
      writeOut(getSliceForWrite());
      buf.clear();
    }
  }

  void writeOut(final ByteBuffer toWrite) throws IOException, ClosedByInterruptException {
    try {
      token = RetryHelper.runWithRetries(new Body<RawGcsCreationToken>() {
        @Override
        public RawGcsCreationToken run() throws IOException {
          return raw.continueObjectCreation(token, toWrite, retryParams.getRequestTimeoutMillis());
        }}, retryParams);
    } catch (ClosedByInterruptException e) {
      token = null;
      throw new ClosedByInterruptException();
    }
  }

  @Override
  public int write(ByteBuffer in) throws IOException {
    synchronized (lock) {
      if (!isOpen()) {
        throw new ClosedChannelException();
      }
      int inBufferSize = in.remaining();
      while (in.hasRemaining()) {
        flushIfNeeded();
        Preconditions.checkState(buf.hasRemaining(), "%s: %s", this, buf);
        int numBytesToCopyToBuffer = Math.min(buf.remaining(), in.remaining());

        int oldLimit = in.limit();
        in.limit(in.position() + numBytesToCopyToBuffer);
        buf.put(in);
        in.limit(oldLimit);
      }
      flushIfNeeded();
      return inBufferSize;
    }
  }

  @Override
  public void waitForOutstandingWrites() throws ClosedByInterruptException, IOException {
    synchronized (lock) {
      int chunkSize = raw.getChunkSizeBytes();
      int position = buf.position();
      int bytesToWrite = (position / chunkSize) * chunkSize;
      if (bytesToWrite > 0) {
        ByteBuffer outputBuffer = getSliceForWrite();
        outputBuffer.limit(bytesToWrite);
        writeOut(outputBuffer);
        buf.position(bytesToWrite);
        buf.limit(position);
        ByteBuffer remaining = buf.slice();
        buf.clear();
        buf.put(remaining);
      }
    }
  }

}
