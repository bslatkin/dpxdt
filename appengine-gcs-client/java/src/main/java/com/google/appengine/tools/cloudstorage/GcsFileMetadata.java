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

import com.google.common.base.Objects;
import com.google.common.base.Preconditions;

/**
 * Contains metadata about a Google Cloud Storage Object.
 */
public final class GcsFileMetadata {

  private final GcsFilename filename;
  private final GcsFileOptions options; private final String etag;
  private final long length;

  public GcsFileMetadata(GcsFilename filename, GcsFileOptions options, String etag, long length) {
    Preconditions.checkArgument(length >= 0, "Length must be positive");
    this.filename = checkNotNull(filename, "Null filename");
    this.options = checkNotNull(options, "Null options");
    this.etag = etag;
    this.length = length;
  }

  public GcsFilename getFilename() {
    return filename;
  }

  public GcsFileOptions getOptions() {
    return options;
  }

  public String getEtag() {
    return etag;
  }

  public long getLength() {
    return length;
  }

  @Override
  public String toString() {
    return getClass().getSimpleName() + "(" + filename + ", " + length + ", " + etag + ", "
        + options + ")";
  }

  @Override
  public final boolean equals(Object o) {
    if (o == this) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    GcsFileMetadata other = (GcsFileMetadata) o;
    return length == other.length && Objects.equal(filename, other.filename)
      && Objects.equal(etag,other.etag) && Objects.equal(options, other.options);
  }

  @Override
  public final int hashCode() {
    return Objects.hashCode(filename, options, etag, length);
  }


}
