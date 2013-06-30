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

import static com.google.common.base.Preconditions.checkArgument;
import static com.google.common.base.Preconditions.checkNotNull;

import com.google.appengine.tools.cloudstorage.RetryHelper.Body;
import com.google.appengine.tools.cloudstorage.RetryHelper.RetryInteruptedException;
import com.google.common.base.Preconditions;

import java.io.IOException;
import java.io.ObjectInputStream;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.ClosedChannelException;
import java.util.concurrent.ExecutionException;

final class SimpleGcsInputChannelImpl implements GcsInputChannel {

  private static final long serialVersionUID = -5076387489828467162L;
  private transient Object lock = new Object();
  private transient RawGcsService raw;
  private final GcsFilename filename;
  private long position;
  private boolean closed = false;
  private boolean eofHit = false;
  private final RetryParams retryParams;

  SimpleGcsInputChannelImpl(
      RawGcsService raw, GcsFilename filename, long startPosition, RetryParams retryParams) {
    this.raw = checkNotNull(raw, "Null raw");
    this.filename = checkNotNull(filename, "Null filename");
    checkArgument(startPosition >= 0, "Start position cannot be negitive");
    this.position = startPosition;
    this.retryParams = retryParams;
  }

  private void readObject(ObjectInputStream aInputStream)
      throws ClassNotFoundException, IOException {
    aInputStream.defaultReadObject();
    lock = new Object();
    raw = GcsServiceFactory.createRawGcsService();
  }

  @Override
  public boolean isOpen() {
    return !closed;
  }

  @Override
  public void close() {
    closed = true;
  }

  @Override
  public int read(final ByteBuffer dst) throws IOException {
    synchronized (lock) {
      if (closed) {
        throw new ClosedChannelException();
      }
      if (eofHit) {
        return -1;
      }
      Preconditions.checkArgument(dst.remaining() > 0, "Requested to read data into a full buffer");
      try {
        return RetryHelper.runWithRetries(new Body<Integer>() {
          @Override
          public Integer run() throws IOException {
            try {
              int n = dst.remaining();
              GcsFileMetadata gcsFileMetadata = raw.readObjectAsync(
                  dst, filename, position, retryParams.getRequestTimeoutMillis()).get();
              int r = n - dst.remaining();
              position += r;
              if (position >= gcsFileMetadata.getLength()) {
                eofHit = true;
              }
              return r == 0 ? -1 : r;
            } catch (ExecutionException e) {
              if (e.getCause() instanceof BadRangeException) {
                eofHit = true;
                return -1;
              } else if (e.getCause() instanceof IOException) {
                throw (IOException) e.getCause();
              } else {
                throw new RuntimeException(this + ": Unexpected cause of ExecutionException", e);
              }
            } catch (InterruptedException e) {
              Thread.currentThread().interrupt();
              closed = true;
              throw new ClosedByInterruptException();
            }
          }
        }, retryParams);
      } catch (RetryInteruptedException e) {
        Thread.currentThread().interrupt();
        closed = true;
        throw new ClosedByInterruptException();
      }
    }
  }
}
