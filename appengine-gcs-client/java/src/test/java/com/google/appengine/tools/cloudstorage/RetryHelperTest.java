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

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import com.google.appengine.tools.cloudstorage.RetryHelper.Body;
import com.google.common.base.Stopwatch;
import com.google.common.base.Ticker;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Tests for Retry helper.
 *
 */
@RunWith(JUnit4.class)
public class RetryHelperTest {

  @Test
  public void testTriesAtLeastMinTimes() throws IOException {
    RetryParams params = new RetryParams.Builder().initialRetryDelayMillis(0)
        .totalRetryPeriodMillis(60000)
        .retryMinAttempts(5)
        .retryMaxAttempts(10)
        .build();
    final int timesToFail = 7;
    int attempted = RetryHelper.runWithRetries(new Body<Integer>() {
      int timesCalled = 0;

      @Override
      public Integer run() throws IOException {
        timesCalled++;
        if (timesCalled <= timesToFail) {
          throw new IOException();
        } else {
          return timesCalled;
        }
      }
    }, params);
    assertEquals(timesToFail + 1, attempted);
  }

  @Test
  public void testTriesNoMoreThanMaxTimes() throws IOException {
    final int maxAttempts = 10;
    RetryParams params = new RetryParams.Builder().initialRetryDelayMillis(0)
        .totalRetryPeriodMillis(60000)
        .retryMinAttempts(0)
        .retryMaxAttempts(maxAttempts)
        .build();
    final AtomicInteger timesCalled = new AtomicInteger(0);
    try {
      RetryHelper.runWithRetries(new Body<Void>() {
        @Override
        public Void run() throws IOException {
          if (timesCalled.incrementAndGet() <= maxAttempts) {
            throw new IOException();
          }
          fail("Body was executed too many times: " + timesCalled.get());
          return null;
        }
      }, params);
      fail("Should not have succeeded, expected all attempts to fail and give up.");
    } catch (RetriesExhaustedException expected) {
      assertEquals(maxAttempts, timesCalled.get());
    }
  }

  private class FakeTicker extends Ticker {
    private final AtomicLong nanos = new AtomicLong();

    /** Advances the ticker value by {@code time} in {@code timeUnit}. */
    FakeTicker advance(long time, TimeUnit timeUnit) {
      return advance(timeUnit.toNanos(time));
    }

    /** Advances the ticker value by {@code nanoseconds}. */
    FakeTicker advance(long nanoseconds) {
      nanos.addAndGet(nanoseconds);
      return this;
    }

    @Override
    public long read() {
      return nanos.get();
    }
  }

  @Test
  public void testTriesNoMoreLongerThanTotalRetryPeriod() throws IOException {
    final FakeTicker ticker = new FakeTicker();
    Stopwatch stopwatch = new Stopwatch(ticker);
    RetryParams params = new RetryParams.Builder().initialRetryDelayMillis(0)
        .totalRetryPeriodMillis(999)
        .retryMinAttempts(5)
        .retryMaxAttempts(10)
        .build();
    final int sleepOnAttempt = 8;
    final AtomicInteger timesCalled = new AtomicInteger(0);
    try {
      RetryHelper.runWithRetries(new Body<Void>() {
        @Override
        public Void run() throws IOException {
          timesCalled.incrementAndGet();
          if (timesCalled.get() == sleepOnAttempt) {
            ticker.advance(1000, TimeUnit.MILLISECONDS);
          }
          throw new IOException();
        }
      }, params, stopwatch);
      fail();
    } catch (RetriesExhaustedException e) {
      assertEquals(sleepOnAttempt, timesCalled.get());
    }
  }

  @Test
  public void testBackoffIsExponential() {
    RetryParams params = new RetryParams.Builder().initialRetryDelayMillis(10)
        .maxRetryDelayMillis(10000000)
        .totalRetryPeriodMillis(60000)
        .retryMinAttempts(0)
        .retryMaxAttempts(100)
        .build();
    final int timesToFail = 200;
    long sleepDuration = RetryHelper.getSleepDuration(params, 1);
    assertTrue("" + sleepDuration, sleepDuration < 10 && sleepDuration >= 5);
    sleepDuration = RetryHelper.getSleepDuration(params, 2);
    assertTrue("" + sleepDuration, sleepDuration < 20 && sleepDuration >= 10);
    sleepDuration = RetryHelper.getSleepDuration(params, 3);
    assertTrue("" + sleepDuration, sleepDuration < 40 && sleepDuration >= 20);
    sleepDuration = RetryHelper.getSleepDuration(params, 4);
    assertTrue("" + sleepDuration, sleepDuration < 80 && sleepDuration >= 40);
    sleepDuration = RetryHelper.getSleepDuration(params, 5);
    assertTrue("" + sleepDuration, sleepDuration < 160 && sleepDuration >= 80);
    sleepDuration = RetryHelper.getSleepDuration(params, 6);
    assertTrue("" + sleepDuration, sleepDuration < 320 && sleepDuration >= 160);
    sleepDuration = RetryHelper.getSleepDuration(params, 7);
    assertTrue("" + sleepDuration, sleepDuration < 640 && sleepDuration >= 320);
    sleepDuration = RetryHelper.getSleepDuration(params, 8);
    assertTrue("" + sleepDuration, sleepDuration < 1280 && sleepDuration >= 640);
    sleepDuration = RetryHelper.getSleepDuration(params, 9);
    assertTrue("" + sleepDuration, sleepDuration < 2560 && sleepDuration >= 1280);
    sleepDuration = RetryHelper.getSleepDuration(params, 10);
    assertTrue("" + sleepDuration, sleepDuration < 5120 && sleepDuration >= 2560);
    sleepDuration = RetryHelper.getSleepDuration(params, 11);
    assertTrue("" + sleepDuration, sleepDuration < 10240 && sleepDuration >= 5120);
    sleepDuration = RetryHelper.getSleepDuration(params, 12);
    assertTrue("" + sleepDuration, sleepDuration < 20480 && sleepDuration >= 10240);
  }

}
