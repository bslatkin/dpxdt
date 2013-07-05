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

package com.google.appengine.tools.cloudstorage.oauth;

import static com.google.common.base.Preconditions.checkNotNull;

import com.google.appengine.api.urlfetch.FetchOptions;
import com.google.appengine.api.urlfetch.HTTPHeader;
import com.google.appengine.api.urlfetch.HTTPMethod;
import com.google.appengine.api.urlfetch.HTTPRequest;
import com.google.appengine.api.urlfetch.HTTPResponse;
import com.google.appengine.api.utils.FutureWrapper;
import com.google.appengine.tools.cloudstorage.BadRangeException;
import com.google.appengine.tools.cloudstorage.GcsFileMetadata;
import com.google.appengine.tools.cloudstorage.GcsFileOptions;
import com.google.appengine.tools.cloudstorage.GcsFilename;
import com.google.appengine.tools.cloudstorage.RawGcsService;
import com.google.common.base.Preconditions;
import com.google.common.collect.ImmutableList;

import java.io.IOException;
import java.io.UnsupportedEncodingException;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Map.Entry;
import java.util.concurrent.Future;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * A wrapper around the Google Cloud Storage REST API.  The subset of features
 * exposed here is intended to be appropriate for implementing
 * {@link RawGcsService}.
 */
final class OauthRawGcsService implements RawGcsService {

  private static final String ACL = "x-goog-acl";
  private static final String CACHE_CONTROL = "Cache-Control";
  private static final String CONTENT_ENCODING = "Content-Encoding";
  private static final String CONTENT_DISPOSITION = "Content-Disposition";
  private static final String CONTENT_TYPE = "Content-Type";
  private static final String ETAG = "ETag";
  private final HTTPHeader versionHeader = new HTTPHeader("x-goog-api-version", "2");

  private static final Logger log = Logger.getLogger(OauthRawGcsService.class.getName());

  public static final List<String> OAUTH_SCOPES =
      ImmutableList.of("https://www.googleapis.com/auth/devstorage.read_write");

  private static final int READ_LIMIT_BYTES = 8 * 1024 * 1024;

  static final int CHUNK_ALIGNMENT_BYTES = 256 * 1024;

  /**
   * Token used during file creation.
   *
   */
  public static class GcsRestCreationToken implements RawGcsCreationToken {
    private static final long serialVersionUID = 975106845036199413L;

    private final GcsFilename filename;
    private final String uploadId;
    private final long offset;

    GcsRestCreationToken(GcsFilename filename,
        String uploadId, long offset) {
      this.filename = checkNotNull(filename, "Null filename");
      this.uploadId = checkNotNull(uploadId, "Null uploadId");
      this.offset = offset;
    }

    @Override
    public GcsFilename getFilename() {
      return filename;
    }

    @Override
    public String toString() {
      return getClass().getSimpleName() + "(" + filename + ", " + uploadId + ")";
    }

    @Override
    public long getOffset() {
      return offset;
    }
  }

  private final OAuthURLFetchService urlfetch;

  OauthRawGcsService(OAuthURLFetchService urlfetch) {
    this.urlfetch = checkNotNull(urlfetch, "Null urlfetch");
  }

  @Override public String toString() {
    return getClass().getSimpleName() + "(" + urlfetch + ")";
  }

  private static URL makeUrl(GcsFilename filename, String uploadId) {
    String encodedFileName;
    try {
      encodedFileName = URLEncoder.encode(filename.getObjectName(), "UTF-8");
    } catch (UnsupportedEncodingException e) {
      throw new RuntimeException(e);
    }
    String s = "https://storage.googleapis.com/" + filename.getBucketName() + "/" + encodedFileName
        + (uploadId == null ? "" : ("?upload_id=" + uploadId));
    try {
      return new URL(s);
    } catch (MalformedURLException e) {
      throw new RuntimeException("Internal error: " + s, e);
    }
  }

  private static HTTPRequest makeRequest(GcsFilename filename, String uploadId,
      HTTPMethod method, long timeoutMillis) {
    return new HTTPRequest(makeUrl(filename, uploadId), method,
        FetchOptions.Builder.disallowTruncate()
            .doNotFollowRedirects()
            .validateCertificate()
            .setDeadline(timeoutMillis / 1000.0));
  }

  private static Error handleError(HTTPRequest req, HTTPResponse resp) throws IOException {
    int responseCode = resp.getResponseCode();
    switch (responseCode) {
      case 400:
        throw new RuntimeException("Server replied with 400, probably bad request: "
            + URLFetchUtils.describeRequestAndResponse(req, resp, true));
      case 401:
        throw new RuntimeException("Server replied with 401, probably bad authentication: "
            + URLFetchUtils.describeRequestAndResponse(req, resp, true));
      case 403:
        throw new RuntimeException(
            "Server replied with 403, check that ACLs are set correctly on the object and bucket: "
            + URLFetchUtils.describeRequestAndResponse(req, resp, true));
      default:
        if (responseCode >= 500 && responseCode < 600) {
          throw new IOException("Response code " + resp.getResponseCode() + ", retryable: "
              + URLFetchUtils.describeRequestAndResponse(req, resp, true));
        } else {
          throw new RuntimeException("Unexpected response code " + resp.getResponseCode() + ": "
              + URLFetchUtils.describeRequestAndResponse(req, resp, true));
        }
    }
  }

  @Override
  public RawGcsCreationToken beginObjectCreation(
      GcsFilename filename, GcsFileOptions options, long timeoutMillis) throws IOException {
    HTTPRequest req = makeRequest(filename, null,
        HTTPMethod.POST, timeoutMillis);
    req.setHeader(new HTTPHeader("x-goog-resumable", "start"));
    req.setHeader(versionHeader);
    addOptionsHeaders(req, options);
    HTTPResponse resp;
    try {
      resp = urlfetch.fetch(req);
    } catch (IOException e) {
      throw new IOException("URLFetch threw IOException; request: "
          + URLFetchUtils.describeRequest(req),
          e);
    }
    if (resp.getResponseCode() == 201) {
      String location = URLFetchUtils.getSingleHeader(resp, "location");
      String marker = "?upload_id=";
      Preconditions.checkState(location.contains(marker),
          "bad location without upload_id: %s", location);
      Preconditions.checkState(!location.contains("&"), "bad location with &: %s", location);
      String uploadId = location.substring(location.indexOf(marker) + marker.length());
      return new GcsRestCreationToken(filename, uploadId, 0);
    } else {
      throw handleError(req, resp);
    }
  }

  private void addOptionsHeaders(HTTPRequest req, GcsFileOptions options) {
    if (options == null) {
      return;
    }
    if (options.getMimeType() != null) {
      req.setHeader(new HTTPHeader(CONTENT_TYPE, options.getMimeType()));
    }
    if (options.getAcl() != null) {
      req.setHeader(new HTTPHeader(ACL, options.getAcl()));
    }
    if (options.getCacheControl() != null) {
      req.setHeader(new HTTPHeader(CACHE_CONTROL, options.getCacheControl()));
    }
    if (options.getContentDisposition() != null) {
      req.setHeader(new HTTPHeader(CONTENT_DISPOSITION, options.getCacheControl()));
    }
    if (options.getContentEncoding() != null) {
      req.setHeader(new HTTPHeader(CONTENT_ENCODING, options.getContentEncoding()));
    }
    for (Entry<String, String> entry : options.getUserMetadata().entrySet()) {
      req.setHeader(new HTTPHeader("x-goog-meta-" + entry.getKey(), entry.getValue()));
    }
  }

  @Override
  public RawGcsCreationToken continueObjectCreation(
      RawGcsCreationToken x, ByteBuffer chunk, long timeoutMillis) throws IOException {
    GcsRestCreationToken token = (GcsRestCreationToken) x;
    int length = chunk.remaining();
    put(token, chunk, false, timeoutMillis);
    return new GcsRestCreationToken(token.filename, token.uploadId, token.offset + length);
  }

  @Override
  public void finishObjectCreation(RawGcsCreationToken x, ByteBuffer chunk, long timeoutMillis)
      throws IOException {
    GcsRestCreationToken token = (GcsRestCreationToken) x;
    put(token, chunk, true, timeoutMillis);
  }

  private void put(GcsRestCreationToken token, ByteBuffer chunk, boolean isFinalChunk,
      long timeoutMillis) throws IOException {
    int length = chunk.remaining();
    long offset = token.offset;
    Preconditions.checkArgument(offset % CHUNK_ALIGNMENT_BYTES == 0,
        "%s: Offset not aligned; offset=%s, length=%s, token=%s",
        this, offset, length, token);
    Preconditions.checkArgument(isFinalChunk || length % CHUNK_ALIGNMENT_BYTES == 0,
        "%s: Chunk not final and not aligned: offset=%s, length=%s, token=%s",
        this, offset, length, token);
    Preconditions.checkArgument(isFinalChunk || length > 0,
        "%s: Chunk empty and not final: offset=%s, length=%s, token=%s",
        this, offset, length, token);
    if (log.isLoggable(Level.FINEST)) {
      log.finest(this + ": About to write to " + token + " " + String.format("0x%x", length)
          + " bytes at offset " + String.format("0x%x", offset)
          + "; isFinalChunk: " + isFinalChunk + ")");
    }
    long limit = offset + length;
    HTTPRequest req = makeRequest(token.filename, token.uploadId,
        HTTPMethod.PUT, timeoutMillis);
    req.setHeader(versionHeader);
    req.setHeader(
        new HTTPHeader("Content-Range",
            "bytes " + (length == 0 ? "*" : offset + "-" + (limit - 1))
            + (isFinalChunk ? "/" + limit : "/*")));
    req.setPayload(peekBytes(chunk));
    HTTPResponse resp;
    try {
      resp = urlfetch.fetch(req);
    } catch (IOException e) {
      throw new IOException(
          "URLFetch threw IOException; request: " + URLFetchUtils.describeRequest(req), e);
    }
    switch (resp.getResponseCode()) {
      case 200:
        if (!isFinalChunk) {
          throw new RuntimeException("Unexpected response code 200 on non-final chunk: "
              + URLFetchUtils.describeRequestAndResponse(req, resp, true));
        } else {
          chunk.position(chunk.limit());
          return;
        }
      case 308:
        if (isFinalChunk) {
          throw new RuntimeException("Unexpected response code 308 on final chunk: "
              + URLFetchUtils.describeRequestAndResponse(req, resp, true));
        } else {
          chunk.position(chunk.limit());
          return;
        }
      default:
        throw handleError(req, resp);
    }
  }

  private static byte[] peekBytes(ByteBuffer in) {
    if (in.hasArray() && in.position() == 0
        && in.arrayOffset() == 0 && in.array().length == in.limit()) {
      return in.array();
    } else {
      int pos = in.position();
      byte[] buf = new byte[in.remaining()];
      in.get(buf);
      in.position(pos);
      return buf;
    }
  }

  /** True if deleted, false if not found. */
  @Override
  public boolean deleteObject(GcsFilename filename, long timeoutMillis) throws IOException {
    HTTPRequest req = makeRequest(filename, null, HTTPMethod.DELETE, timeoutMillis);
    req.setHeader(versionHeader);
    HTTPResponse resp;
    try {
      resp = urlfetch.fetch(req);
    } catch (IOException e) {
      throw new IOException("URLFetch threw IOException; request: "
          + URLFetchUtils.describeRequest(req),
          e);
    }
    switch (resp.getResponseCode()) {
      case 204:
        return true;
      case 404:
        return false;
      default:
        throw handleError(req, resp);
    }
  }

  private long getLengthFromContentRange(HTTPResponse resp) {
    String range = URLFetchUtils.getSingleHeader(resp, "Content-Range");
    Preconditions.checkState(range.matches("bytes [0-9]+-[0-9]+/[0-9]+"),
        "%s: unexpected Content-Range: %s", this, range);
    return Long.parseLong(range.substring(range.indexOf("/") + 1));
  }

  private long getLengthFromContentLength(HTTPResponse resp) {
    return Long.parseLong(URLFetchUtils.getSingleHeader(resp, "Content-Length"));
  }

  /**
   * Might not fill all of dst.
   */
  @Override
  public Future<GcsFileMetadata> readObjectAsync(
      final ByteBuffer dst, final GcsFilename filename, long startOffsetBytes, long timeoutMillis) {
    Preconditions.checkArgument(startOffsetBytes >= 0, "%s: offset must be non-negative: %s",
        this, startOffsetBytes);
    final int n = dst.remaining();
    Preconditions.checkArgument(n > 0, "%s: dst full: %s", this, dst);
    final int want = Math.min(READ_LIMIT_BYTES, n);

    final HTTPRequest req = makeRequest(filename, null, HTTPMethod.GET, timeoutMillis);
    req.setHeader(versionHeader);
    req.setHeader(
        new HTTPHeader("Range", "bytes=" + startOffsetBytes + "-" + (startOffsetBytes + want - 1)));
    return new FutureWrapper<HTTPResponse, GcsFileMetadata>(urlfetch.fetchAsync(req)) {
      @Override
      protected GcsFileMetadata wrap(HTTPResponse resp) throws IOException {
        long totalLength;
        switch (resp.getResponseCode()) {
          case 200:
            totalLength = getLengthFromContentLength(resp);
            break;
          case 206:
            totalLength = getLengthFromContentRange(resp);
            break;
          case 416:
            throw new BadRangeException("Requested Range not satisfiable; perhaps read past EOF? "
                + URLFetchUtils.describeRequestAndResponse(req, resp, true));
          default:
            throw handleError(req, resp);
        }
        byte[] content = resp.getContent();
        Preconditions.checkState(
            content.length <= want, "%s: got %s > wanted %s", this, content.length, want);
        dst.put(content);
        return getMetadataFromResponse(filename, resp, totalLength);
      }

      @Override
      protected Throwable convertException(Throwable e) {
        if (e instanceof IOException || e instanceof BadRangeException) {
          return e;
        } else {
          return new IOException(
              "URLFetch threw IOException; request: " + URLFetchUtils.describeRequest(req), e);
        }
      }
    };
  }

  @Override
  public GcsFileMetadata getObjectMetadata(GcsFilename filename, long timeoutMillis)
      throws IOException {
    HTTPRequest req = makeRequest(filename, null, HTTPMethod.HEAD, timeoutMillis);
    req.setHeader(versionHeader);
    HTTPResponse resp;
    try {
      resp = urlfetch.fetch(req);
    } catch (IOException e) {
      throw new IOException(
          "URLFetch threw IOException; request: " + URLFetchUtils.describeRequest(req), e);
    }
    int responseCode = resp.getResponseCode();
    if (responseCode == 404) {
      return null;
    }
    if (responseCode != 200) {
      throw handleError(req, resp);
    }
    return getMetadataFromResponse(filename, resp, getLengthFromContentLength(resp));
  }

  private GcsFileMetadata getMetadataFromResponse(
      GcsFilename filename, HTTPResponse resp, long length) {
    List<HTTPHeader> headers = resp.getHeaders();
    GcsFileOptions.Builder optionsBuilder = new GcsFileOptions.Builder();
    String etag = null;
    for (HTTPHeader header : headers) {
      if (header.getName().startsWith("x-goog-meta-")) {
        String key = header.getName().replaceFirst("x-goog-meta-", "");
        String value = header.getValue();
        optionsBuilder.addUserMetadata(key, value);
      }
      if (header.getName().equals(ACL)) {
        optionsBuilder.acl(header.getValue());
      }
      if (header.getName().equals(CACHE_CONTROL)) {
        optionsBuilder.cacheControl(header.getValue());
      }
      if (header.getName().equals(CONTENT_ENCODING)) {
        optionsBuilder.contentEncoding(header.getValue());
      }
      if (header.getName().equals(CONTENT_DISPOSITION)) {
        optionsBuilder.contentDisposition(header.getValue());
      }
      if (header.getName().equals(CONTENT_TYPE)) {
        optionsBuilder.mimeType(header.getValue());
      }
      if (header.getName().equals(ETAG)) {
        etag = header.getValue();
      }
    }
    GcsFileOptions options = optionsBuilder.build();

    return new GcsFileMetadata(filename, options, etag, length);
  }

  @Override
  public int getChunkSizeBytes() {
    return CHUNK_ALIGNMENT_BYTES;
  }

}
