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

package com.google.appengine.tools.cloudstorage.dev;

import static com.google.common.base.Preconditions.checkNotNull;

import com.google.appengine.api.datastore.Blob;
import com.google.appengine.api.datastore.DatastoreService;
import com.google.appengine.api.datastore.DatastoreServiceFactory;
import com.google.appengine.api.datastore.Entity;
import com.google.appengine.api.datastore.EntityNotFoundException;
import com.google.appengine.api.datastore.Key;
import com.google.appengine.api.datastore.KeyFactory;
import com.google.appengine.api.datastore.Transaction;
import com.google.appengine.api.files.AppEngineFile;
import com.google.appengine.api.files.FileReadChannel;
import com.google.appengine.api.files.FileService;
import com.google.appengine.api.files.FileServiceFactory;
import com.google.appengine.api.files.FileStat;
import com.google.appengine.api.files.FileWriteChannel;
import com.google.appengine.api.files.GSFileOptions;
import com.google.appengine.api.files.GSFileOptions.GSFileOptionsBuilder;
import com.google.appengine.tools.cloudstorage.BadRangeException;
import com.google.appengine.tools.cloudstorage.GcsFileMetadata;
import com.google.appengine.tools.cloudstorage.GcsFileOptions;
import com.google.appengine.tools.cloudstorage.GcsFilename;
import com.google.appengine.tools.cloudstorage.RawGcsService;
import com.google.common.base.Objects;
import com.google.common.base.Preconditions;
import com.google.common.util.concurrent.Futures;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.nio.ByteBuffer;
import java.util.Map.Entry;
import java.util.concurrent.Future;

/**
 * Implementation of {@code RawGcsService} for dev_appserver. For now, uses datastore and
 * fileService so that the viewers can be re-used.
 */
final class LocalRawGcsService implements RawGcsService {

  static final int CHUNK_ALIGNMENT_BYTES = 256 * 1024;

  private static final DatastoreService DATASTORE = DatastoreServiceFactory.getDatastoreService();
  private static final FileService FILES = FileServiceFactory.getFileService();

  private static final String ENTITY_KIND_PREFIX = "_ah_FakeCloudStorage__";
  private static final String OPTIONS_PROP = "options";

  static final class Token implements RawGcsCreationToken {
    private static final long serialVersionUID = 954846981243798905L;

    private final GcsFilename filename;
    private final GcsFileOptions options;
    private final long offset;
    private final AppEngineFile file;

    Token(GcsFilename filename, GcsFileOptions options, long offset, AppEngineFile file) {
      this.options = options;
      this.filename = checkNotNull(filename, "Null filename");
      this.offset = offset;
      this.file = checkNotNull(file, "Null file");
    }

    @Override
    public GcsFilename getFilename() {
      return filename;
    }

    @Override
    public long getOffset() {
      return offset;
    }

    @Override
    public String toString() {
      return getClass().getSimpleName() + "(" + filename + ", " + offset + ")";
    }

    @Override
    public final boolean equals(Object o) {
      if (o == this) {
        return true;
      }
      if (o == null || getClass() != o.getClass()) {
        return false;
      }
      Token other = (Token) o;
      return offset == other.offset && Objects.equal(filename, other.filename)
          && Objects.equal(options, other.options);
    }

    @Override
    public final int hashCode() {
      return Objects.hashCode(filename, offset, options);
    }
  }

  @Override
  public Token beginObjectCreation(GcsFilename filename, GcsFileOptions options, long timeoutMillis)
      throws IOException {
    return new Token(
        filename, options, 0, FILES.createNewGSFile(gcsOptsToGsOpts(filename, options)));
  }

  private GSFileOptions gcsOptsToGsOpts(GcsFilename filename, GcsFileOptions options) {
    GSFileOptionsBuilder builder = new GSFileOptionsBuilder();
    builder.setBucket(filename.getBucketName());
    builder.setKey(filename.getObjectName());
    if (options.getAcl() != null) {
      builder.setAcl(options.getAcl());
    }
    if (options.getCacheControl() != null) {
      builder.setCacheControl(options.getCacheControl());
    }
    if (options.getContentDisposition() != null) {
      builder.setContentDisposition(options.getContentDisposition());
    }
    if (options.getContentEncoding() != null) {
      builder.setContentEncoding(options.getContentEncoding());
    }
    if (options.getMimeType() != null) {
      builder.setMimeType(options.getMimeType());
    }
    for (Entry<String, String> entry : options.getUserMetadata().entrySet()) {
      builder.addUserMetadata(entry.getKey(), entry.getValue());
    }
    return builder.build();
  }

  private Token append(RawGcsCreationToken token, ByteBuffer chunk) throws IOException {
    Token t = (Token) token;
    FileWriteChannel ch = FILES.openWriteChannel(t.file, false);
    int n = chunk.remaining();
    try {
      int r = ch.write(chunk);
      Preconditions.checkState(r == n, "%s: Bad write: %s != %s", this, r, n);
    } finally {
      ch.close();
    }
    return new Token(t.filename, t.options, t.offset + n, t.file);
  }

  @Override
  public RawGcsCreationToken continueObjectCreation(
      RawGcsCreationToken token, ByteBuffer chunk, long timeoutMillis) throws IOException {
    return append(token, chunk);
  }

  private Key makeKey(GcsFilename filename) {
    return KeyFactory.createKey(
        ENTITY_KIND_PREFIX + filename.getBucketName(), filename.getObjectName());
  }

  @Override
  public void finishObjectCreation(RawGcsCreationToken token, ByteBuffer chunk, long timeoutMillis)
      throws IOException {
    Token t = append(token, chunk);
    FILES.openWriteChannel(t.file, true).closeFinally();
    Entity e = new Entity(makeKey(t.filename));
    ByteArrayOutputStream bout = new ByteArrayOutputStream();
    ObjectOutputStream oout = new ObjectOutputStream(bout);
    oout.writeObject(t.options);
    oout.close();
    e.setUnindexedProperty(OPTIONS_PROP, new Blob(bout.toByteArray()));
    DATASTORE.put(null, e);
  }

  private AppEngineFile nameToAppEngineFile(GcsFilename filename) {
    return new AppEngineFile(
        AppEngineFile.FileSystem.GS, filename.getBucketName() + "/" + filename.getObjectName());
  }


  @Override
  public GcsFileMetadata getObjectMetadata(GcsFilename filename, long timeoutMillis)
      throws IOException {
    Entity e;
    try {
      e = DATASTORE.get(null, makeKey(filename));
    } catch (EntityNotFoundException ex) {
      return null;
    }
    AppEngineFile file = nameToAppEngineFile(filename);
    ObjectInputStream in = new ObjectInputStream(
        new ByteArrayInputStream(((Blob) e.getProperty(OPTIONS_PROP)).getBytes()));
    GcsFileOptions options;
    try {
      options = (GcsFileOptions) in.readObject();
    } catch (ClassNotFoundException e1) {
      throw new RuntimeException(e1);
    } finally {
      in.close();
    }
    FileStat stat = FILES.stat(file);
    return new GcsFileMetadata(filename, options, null, FILES.stat(file).getLength());
  }

  @Override
  public Future<GcsFileMetadata> readObjectAsync(
      ByteBuffer dst, GcsFilename filename, long offset, long timeoutMillis) {
    Preconditions.checkArgument(offset >= 0, "%s: offset must be non-negative: %s", this, offset);
    try {
      GcsFileMetadata meta = getObjectMetadata(filename, timeoutMillis);
      if (meta == null) {
        return Futures.immediateFailedFuture(
            new FileNotFoundException(this + ": No such file: " + filename));
      }
      if (offset >= meta.getLength()) {
        return Futures.immediateFailedFuture(new BadRangeException(
            "The requested range cannot be satisfied. bytes=" + Long.toString(offset) + "-"
            + Long.toString(offset + dst.remaining()) + " the file is only " + meta.getLength()));
      }
      AppEngineFile file = nameToAppEngineFile(filename);
      FileReadChannel readChannel = FILES.openReadChannel(file, false);
      readChannel.position(offset);
      int read = 0;
      while (read != -1 && dst.hasRemaining()) {
        read = readChannel.read(dst);
      }
      return Futures.immediateFuture(meta);
    } catch (IOException e) {
      return Futures.immediateFailedFuture(e);
    }
  }

  @Override
  public boolean deleteObject(GcsFilename filename, long timeoutMillis) throws IOException {
    AppEngineFile file = nameToAppEngineFile(filename);
    if (file == null) {
      return false;
    }

    DATASTORE.delete((Transaction) null, makeKey(filename));
    FILES.delete(file);
    return true;
  }

  @Override
  public int getChunkSizeBytes() {
    return CHUNK_ALIGNMENT_BYTES;
  }

}
