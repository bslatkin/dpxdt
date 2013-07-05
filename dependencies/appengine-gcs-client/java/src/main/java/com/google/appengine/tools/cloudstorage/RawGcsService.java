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

import java.io.IOException;
import java.io.Serializable;
import java.nio.ByteBuffer;
import java.util.concurrent.Future;

/**
 * Low-level ("raw") interface to Google Cloud Storage. This interface need not be used or seen by
 * users of Google Cloud Storage. Instead the higher level API {@link GcsService} should be used.
 *
 * <p>
 * Methods throw IOException for connection errors etc. that are retryable, and other exceptions for
 * bad requests and similar errors that should not be retried.
 *
 * <p>
 * Implementing classes handle authentication through mechanisms not exposed in this interface.
 */
public interface RawGcsService {

  /**
   * Calls to {@link #continueObjectCreation(RawGcsCreationToken, ByteBuffer, long)}
   * need to pass fixed size chunks.
   *
   * This returns the size expected by the implementation.
   */
  public int getChunkSizeBytes();

  /**
   * Immutable token that wraps the information a specific implementation of
   * {@link RawGcsService} needs to write to an object.
   *
   * Instances of this interface are only usable with the type of
   * {@link RawGcsService} that created them.
   */
  interface RawGcsCreationToken extends Serializable {
    /**
     * The Filename of the object being written.
     */
    GcsFilename getFilename();

    /**
     * The number of bytes written to the object so far.
     */
    long getOffset();
  }

  /**
   * @param options null means let Google Cloud Storage use its default
   */
  RawGcsCreationToken beginObjectCreation(
      GcsFilename filename,
      GcsFileOptions options,
      long timeoutMillis)
      throws IOException;

  /**
   * Reads all remaining bytes from {@code chunk} and writes them to the object
   * and offset specified by {@code token}.
   *
   * <p>Returns a new token to be used to continue writing to the object.
   * Does not mutate {@code token}.
   *
   * <p>The number of bytes remaining in {@code chunk} must be a nonzero multiple
   * of {@link #getChunkSizeBytes()} and may be subject to an upper limit that
   * is implementation-dependent.
   *
   * <p>On error, does not consume any bytes from {@code chunk}.  The write may
   * be retried by making another call with the same {@code token}.  A whole
   * sequence of writes may be retried by using a previous token (this is useful
   * if the calling code crashes and rolls back to an earlier state).  In both
   * cases, the calling code is responsible for guaranteeing that the byte
   * sequence written to the object remains identical across retries.  (This is
   * because the write may have succeeded on the backend even though an
   * exception was thrown by this method, and writing different data on a retry
   * leaves the object in a bad state.)
   */
  RawGcsCreationToken continueObjectCreation(RawGcsCreationToken token,
      ByteBuffer chunk, long timeoutMillis)
      throws IOException;

  /**
   * Reads all remaining bytes from {@code chunk} and writes them to the object
   * and offset specified by {@code token}, as the final bytes of the object.
   * The object will become readable, and further writes will be rejected.
   *
   * <p>The number of bytes remaining in {@code chunk} may be subject to an
   * upper limit that is implementation-dependent.
   *
   * <p>On error, does not consume any bytes from {@code chunk}.  The write may
   * be retried by making another call with the same {@code token}.  A whole
   * sequence of writes may be retried by using a previous token (this is useful
   * if the calling code crashes and rolls back to an earlier state).  In both
   * cases, the calling code is responsible for guaranteeing that the byte
   * sequence written to the object remains identical across retries.  (This is
   * because the write may have succeeded on the backend even though an
   * exception was thrown by this method, and writing different data on a retry
   * leaves the object in a bad state.)
   */
  void finishObjectCreation(RawGcsCreationToken token,
      ByteBuffer chunk, long timeoutMillis)
      throws IOException;

  /**
   * Issues a request to the server to retrieve data to fill the provided buffer.
   * The {@code offset} may not be negative.
   */
  Future<GcsFileMetadata> readObjectAsync(ByteBuffer dst, GcsFilename filename, long offset,
      long timeoutMillis);

  /**
   *
   */
  GcsFileMetadata getObjectMetadata(GcsFilename filename, long timeoutMillis) throws IOException;

  /**
   * Returns true if deleted, false if not found.
   */
  boolean deleteObject(GcsFilename filename, long timeoutMillis) throws IOException;

}
