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

import java.io.Serializable;

/**
 * Bucket and object name of a Google Cloud Storage object.
 */
public final class GcsFilename implements Serializable {
  private static final long serialVersionUID = 973785057408880204L;

  private final String bucketName;
  private final String objectName;

  public GcsFilename(String bucketName, String objectName) {
    this.bucketName = checkNotNull(bucketName, "Null bucketName");
    this.objectName = checkNotNull(objectName, "Null objectName");
  }

  public String getBucketName() {
    return bucketName;
  }

  public String getObjectName() {
    return objectName;
  }

  @Override
  public String toString() {
    return getClass().getSimpleName() + "(" + bucketName + ", " + objectName + ")";
  }

  @Override
  public final boolean equals(Object o) {
    if (o == this) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    GcsFilename other = (GcsFilename) o;
    return Objects.equal(bucketName, other.bucketName)
        && Objects.equal(objectName, other.objectName);
  }

  @Override
  public final int hashCode() {
    return Objects.hashCode(bucketName, objectName);
  }

}
