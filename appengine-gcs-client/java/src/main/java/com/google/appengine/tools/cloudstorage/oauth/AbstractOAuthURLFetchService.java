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

import com.google.appengine.api.urlfetch.HTTPHeader;
import com.google.appengine.api.urlfetch.HTTPRequest;
import com.google.appengine.api.urlfetch.HTTPResponse;
import com.google.appengine.api.urlfetch.URLFetchService;
import com.google.appengine.api.urlfetch.URLFetchServiceFactory;

import java.io.IOException;
import java.util.concurrent.Future;

/**
 * An OAuthURLFetchService decorator that adds the authorization header to the http request.
 */
abstract class AbstractOAuthURLFetchService implements OAuthURLFetchService {

  private static final URLFetchService URLFETCH = URLFetchServiceFactory.getURLFetchService();

  AbstractOAuthURLFetchService() {}

  protected abstract String getAuthorization();

  private HTTPRequest authorizeRequest(HTTPRequest req) {
    req = URLFetchUtils.copyRequest(req);
    req.setHeader(new HTTPHeader("Authorization", getAuthorization()));
    return req;
  }

  @Override
  public HTTPResponse fetch(HTTPRequest req) throws IOException {
    return URLFETCH.fetch(authorizeRequest(req));
  }

  @Override
  public Future<HTTPResponse> fetchAsync(HTTPRequest req) {
    return URLFETCH.fetchAsync(authorizeRequest(req));
  }


}
