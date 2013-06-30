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
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.WritableByteChannel;

/**
 * A writable byte channel for writing data to Google Cloud Storage. Write calls will either place
 * the data into an internal buffer or make a synchronous RPC call to write the data.
 *
 *  Implementations of this class may further buffer data internally to reduce remote calls.
 *
 * Calling {@link #close()} will cause any buffers to be flushed and all data written to be stored
 * durably. After this point the file can be read but no longer written to. Not calling close will
 * result in the file not ever being written durably and it will automatically disappear from Google
 * Cloud Storage.
 *
 *  This class is serializable, this allows for writing part of a file, serializing the
 * GcsOutputChannel deserializing it, and continuing to write to the same file. The time for which a
 * serialized instance is valid is limited and determined by the Google Cloud Storage service. Note
 * that this is not intended as a way to create multiple GcsOutputChannel objects for the same file.
 * Even if one serializes and deserialzes this object, only one of the original instance or the
 * deserialized instance may be used going forward. Using both in parallel will result in undefined
 * behavior.
 */
public interface GcsOutputChannel extends WritableByteChannel, Serializable {

  /**
   * Returns the filename.
   */
  GcsFilename getFilename();

  /**
   * @return The size of the buffer used internally by this class. (0 if the data is unbuffered)
   */
  int getBufferSizeBytes();

  /**
   * @param src A byte buffer that should be written to the end of the file. This buffer may be of
   *        any size, but writes are not guaranteed to be durable until {@link #close()} is called.
   *
   * @throws IOException An error occurred writing the data. If an IOException is thrown none or
   *         part of the data may have been written. For this reason it may be best to start writing
   *         the file from the beginning. This can be avoided by providing a retry policy when
   *         constructing this class.
   * @return Will always write (or buffer) the full buffer passed in. As such it will return the
   *         size of the provided buffer.
   *
   * @see WritableByteChannel#write(ByteBuffer)
   */
  @Override
  public int write(ByteBuffer src) throws IOException;
  
  
  /**
   * Blocks until all data that can be written has been written.
   *
   * It is possible that not all data can be written as GCS requires non-final writes to be fixed
   * sizes.
   *
   * This method is most useful to call before serialization, as it will minimize the size of the
   * serialized object.
   */
  void waitForOutstandingWrites() throws ClosedByInterruptException, IOException;

  /**
   * Flushes any buffers and writes all data to durable storage. Once {@link #close()} is called
   * further calls to #write(ByteBuffer) will fail. This must be called before the file can be read.
   *
   * If close is not called all data written will be automatically deleted after some time. (This
   * may be desirable if an unrecoverable error occurred while writing the file)
   *
   * Note that calling close will also invalidate any serialized instances of this class, so it
   * should NOT be called if one is planning to serialize this object with the intention to resume
   * writing to the file later.
   *
   * @see WritableByteChannel#close()
   */
  @Override
  public void close() throws IOException;

}
