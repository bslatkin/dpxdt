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

import com.google.appengine.api.appidentity.AppIdentityService;
import com.google.appengine.api.appidentity.AppIdentityServiceFactory;
import com.google.appengine.api.utils.SystemProperty;
import com.google.common.collect.ImmutableList;

import java.util.List;

/**
 * {@link OAuthURLFetchService} based on {@link AppIdentityService}. This will work in production
 * without any need for credential passing (assuming the service account is given permission to the
 * Google Cloud Storage bucket), but it won't work locally running against real Google Cloud
 * Storage.
 */
final class AppIdentityOAuthURLFetchService extends AbstractOAuthURLFetchService {

  private final List<String> oauthScopes;

  AppIdentityOAuthURLFetchService(List<String> oauthScopes) {
    this.oauthScopes = ImmutableList.copyOf(oauthScopes);
  }

  @Override
  protected String getAuthorization() {
    String accessToken = AppIdentityServiceFactory.getAppIdentityService()
        .getAccessToken(oauthScopes).getAccessToken();
    if (SystemProperty.environment.value() == SystemProperty.Environment.Value.Development) {
      throw new RuntimeException(
          this + ": The access token from the development environment won't work: " + accessToken);
    }
    return "Bearer " + accessToken;
  }

}
