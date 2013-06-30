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

/**
 * {@link OAuthURLFetchService} that uses a fixed token, as a quick hack to allow the dev_appserver
 * to talk to real Google Cloud Storage.
 */
final class FixedTokenOAuthURLFetchService extends AbstractOAuthURLFetchService {

  private final String token;

  public FixedTokenOAuthURLFetchService(String token) {
    this.token = checkNotNull(token, "Null token");
  }

  @Override
  protected String getAuthorization() {
    return "Bearer " + token;
  }

}
