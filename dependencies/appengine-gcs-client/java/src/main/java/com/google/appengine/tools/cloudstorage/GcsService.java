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

/**
 * Allows creating and accessing files in Google Cloud Storage.
 *
 * This class uses the {@link RetryParams} that were passed to {@link GcsServiceFactory}. This is
 * used for all of the methods provided by this class. So an {@link RetriesExhaustedException} means
 * that these have failed. Retry logic is handled internally to this class, because while writing to
 * the {@link GcsOutputChannel} a request can span the boundaries of segments written to
 * {@link RawGcsService}. As a result a write call could partly succeed, making error recovery at an
 * application level next to impossible.
 *
 * Reading, deleting, and gettingMetadata are all idempotent operations. However for symmetry and
 * convenience the {@link RetryParams} are applied to these calls as well.
 */
public interface GcsService {

  /**
   * Creates a new object.
   *
   * Closing the channel will finalize the file.
   */
  GcsOutputChannel createOrReplace(GcsFilename filename, GcsFileOptions options)
      throws IOException;


  /**
   * Note that the implementation may check if the file exists during the call to
   * {@code openReadChannel}, or only check it when the first byte is requested.
   *
   * If buffering is desired openPrefetchingReadChannel should be called instead.
   */
  GcsInputChannel openReadChannel(GcsFilename filename, long startPosition) throws IOException;

  /**
   * Same as openReadChannel but buffers data in memory and prefetches it before it is required to
   * attempt to avoid blocking on every read call.
   *
   * If some data is already available locally (prefetched), but not enough to fill the dst buffer,
   * the returned channel might fill only part of it, to avoid blocking.
   */
  GcsInputChannel openPrefetchingReadChannel(
      GcsFilename filename, long startPosition, int blockSizeBytes);

  /**
   * @param filename The name of the file that you wish to read the metadata of.
   * @return The metadata associated with the file, or null if the file does not exist.
   * @throws IOException If for any reason the file can't be read.
   */
  GcsFileMetadata getMetadata(GcsFilename filename) throws IOException;

  /**
   * Returns true if deleted, false if not found.
   */
  boolean delete(GcsFilename filename) throws IOException;

}
