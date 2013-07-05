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

import static java.util.concurrent.TimeUnit.MILLISECONDS;

import com.google.apphosting.api.ApiProxy.ApiProxyException;
import com.google.common.base.Stopwatch;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.net.MalformedURLException;
import java.nio.channels.ClosedByInterruptException;
import java.util.logging.Logger;

/**
 * Utility class for retrying operations. For more details about the parameters, see
 * {@link RetryParams}
 *
 * If the request is never successful, a {@link RetriesExhaustedException} will be thrown.
 *
 * @author ohler@google.com (Christian Ohler)
 *
 * @param <V> return value of the closure that is being run with retries
 */
public class RetryHelper<V> {

  private static final Logger log = Logger.getLogger(RetryHelper.class.getName());

  private static String messageChain(Throwable t) {
    StringBuilder resultMessage = new StringBuilder("" + t);
    t = t.getCause();
    while (t != null) {
      resultMessage.append("\n -- caused by: " + t);
      t = t.getCause();
    }
    return "" + resultMessage;
  }

  /** Body to be run and retried if it doesn't succeed. */
  interface Body<V> {
    V run() throws IOException;
  }

  static class RetryInteruptedException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    RetryInteruptedException() {
    }
  }

  private final Stopwatch stopwatch;
  private int attemptsSoFar = 0;
  private final Body<V> body;
  private final RetryParams retryParams;

  private RetryHelper(Body<V> body, RetryParams parms) {
    this(body, parms, new Stopwatch());
  }

  private RetryHelper(Body<V> body, RetryParams parms, Stopwatch stopwatch) {
    this.body = body;
    this.retryParams = parms;
    this.stopwatch = stopwatch;
  }


  @Override
  public String toString() {
    return getClass().getSimpleName() + "(" + stopwatch + ", " + attemptsSoFar + " attempts, "
        + body + ")";
  }

  private V doRetry() throws IOException {
    stopwatch.start();
    while (true) {
      attemptsSoFar++;
      Exception exception;
      try {
        V value = body.run();
        if (attemptsSoFar > 1) {
          log.info(this + ": retry successful");
        }
        return value;
      } catch (IOException e) {
        if (e instanceof FileNotFoundException || e instanceof MalformedURLException
            || e instanceof ClosedByInterruptException) {
          throw e;
        }
        exception = e;
      } catch (ApiProxyException e) {
        exception = e;
      }
      long sleepDurationMillis = getSleepDuration(retryParams, attemptsSoFar);

      log.warning(this + ": Attempt " + attemptsSoFar + " failed, sleeping for "
          + sleepDurationMillis + " ms: " + messageChain(exception));

      if (attemptsSoFar >= retryParams.getRetryMaxAttempts() || (
          attemptsSoFar >= retryParams.getRetryMinAttempts()
          && stopwatch.elapsed(MILLISECONDS) >= retryParams.getTotalRetryPeriodMillis())) {
        throw new RetriesExhaustedException(this + ": Too many failures, giving up", exception);
      }
      try {
        Thread.sleep(sleepDurationMillis);
      } catch (InterruptedException e2) {
        Thread.currentThread().interrupt();
        throw new RetryInteruptedException();
      }
    }
  }

  static long getSleepDuration(RetryParams retryParams, int attemptsSoFar) {
    return (long) ((Math.random() / 2.0 + .5) * (Math.min(
        retryParams.getMaxRetryDelayMillis(),
            Math.pow(retryParams.getRetryDelayBackoffFactor(), attemptsSoFar - 1)
            * retryParams.getInitialRetryDelayMillis())));
  }

  public static <V> V runWithRetries(Body<V> body) throws IOException {
    return new RetryHelper<V>(body, RetryParams.getDefaultInstance()).doRetry();
  }

  public static <V> V runWithRetries(Body<V> body, RetryParams parms) throws IOException {
    return new RetryHelper<V>(body, parms).doRetry();
  }
  /**
   * For testing.
   */
  static <V> V runWithRetries(Body<V> body, RetryParams parms, Stopwatch stopwatch)
      throws IOException {
    return new RetryHelper<V>(body, parms, stopwatch).doRetry();
  }

}
