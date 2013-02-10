#!/usr/bin/env python

"""Utility for doing incremental diffs for a live website."""

import HTMLParser
import Queue
import json
import logging
import os
import re
import shutil
import sys
import urlparse


# Local Libraries
import gflags
import workers


FLAGS = gflags.FLAGS

gflags.DEFINE_string(
    'output_dir', None,
    'Directory where the output should be saved. If it does not exist '
    'it will be created.')

gflags.DEFINE_string(
    'reference_dir', None,
    'Directory where this tool last ran; used for generating new diffs. '
    'When empty, no diffs will be made.')

gflags.DEFINE_spaceseplist(
    'ignore_prefixes', [],
    'URL prefixes that should not be crawled.')


class Error(Exception):
  """Base class for exceptions in this module."""

class CaptureFailedError(Error):
  """Capturing a page screenshot failed."""


# URL regex rewriting code originally from mirrorrr
# http://code.google.com/p/mirrorrr/source/browse/trunk/transform_content.py

# URLs that are relative to the base of the current hostname.
BASE_RELATIVE_URL_REGEX = (
    r"/(?!(/)|(http(s?)://)|(url\())(?P<url>[^\"'> \t\)]*)")
# URLs that have '../' or './' to start off their paths.
TRAVERSAL_URL_REGEX = (
    r"(?P<relative>\.(\.)?)/(?!(/)|"
    r"(http(s?)://)|(url\())(?P<url>[^\"'> \t\)]*)")
# URLs that are in the same directory as the requested URL.
SAME_DIR_URL_REGEX = r"(?!(/)|(http(s?)://)|(#)|(url\())(?P<url>[^\"'> \t]+)"
# URL matches the root directory.
ROOT_DIR_URL_REGEX = r"(?!//(?!>))/(?P<url>)(?=[ \t\n]*[\"'\)>/])"
# Start of a tag using 'src' or 'href'
TAG_START = (
    r"(?i)(?P<tag>\ssrc|href|action|url|background)"
    r"(?P<equals>[\t ]*=[\t ]*)(?P<quote>[\"']?)")
# Potential HTML document URL with no fragments.
MAYBE_HTML_URL_REGEX = TAG_START + r"(?P<absurl>http(s?)://[^\"'> \t#]+)"

REPLACEMENT_REGEXES = [
  (TAG_START + SAME_DIR_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(accessed_dir)s\g<url>"),
  (TAG_START + TRAVERSAL_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(accessed_dir)s/\g<relative>/\g<url>"),
  (TAG_START + BASE_RELATIVE_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(base)s/\g<url>"),
  (TAG_START + ROOT_DIR_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(base)s/"),
]


def extract_urls(url, data, unescape=HTMLParser.HTMLParser().unescape):
  """Extracts the URLs from an HTML document."""
  parts = urlparse.urlparse(url)
  prefix = '%s://%s' % (parts.scheme, parts.netloc)

  accessed_dir = os.path.dirname(parts.path)
  if not accessed_dir.endswith('/'):
    accessed_dir += '/'

  for pattern, replacement in REPLACEMENT_REGEXES:
    fixed = replacement % {
      'base': prefix,
      'accessed_dir': accessed_dir,
    }
    data = re.sub(pattern, fixed, data)

  result = set()
  for match in re.finditer(MAYBE_HTML_URL_REGEX, data):
    found_url = unescape(match.groupdict()['absurl'])
    result.add(found_url)
  return result


IGNORE_SUFFIXES = frozenset([
    'jpg', 'jpeg', 'png', 'css', 'js', 'xml', 'json', 'gif', 'ico', 'doc'])


def prune_urls(url_set, start_url, allowed_list, ignored_list):
  """Prunes URLs that should be ignored."""
  result = set()

  for url in url_set:
    allowed = False
    for allow_url in allowed_list:
      if url.startswith(allow_url):
        allowed = True
        break

    if not allowed:
      continue

    parts = urlparse.urlparse(url)
    if parts.query or parts.fragment:
      continue

    ignored = False
    for ignore_url in ignored_list:
      if url.startswith(ignore_url):
        ignored = True
        break

    if ignored:
      continue

    prefix, suffix = (url.rsplit('.', 1) + [''])[:2]
    if suffix.lower() in IGNORE_SUFFIXES:
      continue

    result.add(url)

  return result


class PdiffWorkflow(workers.WorkflowItem):
  """Workflow for generating Pdiffs."""

  def run(self, url, output_dir, reference_dir):
    parts = urlparse.urlparse(url)
    clean_url = (
      parts.path.replace('/', '_').replace('\\', '_')
      .replace(':', '_').replace('.', '_'))
    output_base = os.path.join(output_dir, clean_url)

    config_path = output_base + '_config.js'
    with open(config_path, 'w') as config_file:
      # TODO: Take the base config from a standard file or flags.
      config_file.write(json.dumps({
        'targetUrl': url,
        'viewportSize': {
          'width': 1024,
          'height': 768,
        }
      }))

    capture = yield workers.CaptureItem(
      output_base + '_run.log',
      config_path,
      output_base + '_run.png')

    if capture.returncode != 0:
      raise CaptureFailedError('Failed to capture url=%r' % url)

    if not reference_dir:
      return

    ref_base = os.path.join(reference_dir, clean_url)
    last_run = ref_base + '_run.png'
    if not os.path.exists(last_run):
      return

    last_log = ref_base + '_run.log'
    if not os.path.exists(last_log):
      return

    ref_output = output_base + '_ref.png'
    ref_log = output_base + '_ref.log'
    shutil.copy(last_run, ref_output)
    shutil.copy(last_log, ref_log)

    diff_output = output_base + '_diff.png'
    diff = yield workers.DiffItem(
        output_base + '_diff.log',
        ref_output,
        capture.output_path,
        diff_output)

    if diff.returncode != 0 and os.path.exists(diff_output):
      print 'Found diff for path=%r, diff=%r' % (parts.path, diff_output)


class SiteDiff(workers.WorkflowItem):
  """Workflow for coordinating the site diff."""

  def run(self, start_url, ignore_prefixes, output_dir, reference_dir):
    if not os.path.isdir(output_dir):
      os.mkdir(output_dir)

    pending_urls = set([start_url])
    seen_urls = set()
    good_urls = set()

    while pending_urls:
      seen_urls.update(pending_urls)
      output = yield [workers.FetchItem(u) for u in pending_urls]
      pending_urls.clear()

      for item in output:
        if not item.data:
          logging.info('No data from url=%r', item.url)
          continue

        if item.headers.gettype() != 'text/html':
          logging.info('Skipping non-HTML document url=%r', item.url)
          continue

        good_urls.add(item.url)
        found = extract_urls(item.url, item.data)
        pruned = prune_urls(
            found, start_url, [start_url], ignore_prefixes)
        new = pruned - seen_urls
        pending_urls.update(new)

    print 'Found %d total URLs, %d good HTML pages' % (
        len(seen_urls), len(good_urls))

    found_urls = os.path.join(output_dir, 'url_paths.txt')
    good_paths = set(urlparse.urlparse(u).path for u in good_urls)
    with open(found_urls, 'w') as urls_file:
      urls_file.write('\n'.join(sorted(good_paths)))

    results = []
    for url in good_urls:
      results.append(PdiffWorkflow(url, output_dir, reference_dir))
    results = yield results

    # TODO: Check for outputs? What about failure cases?


def real_main(url, ignore_prefixes, output_dir, reference_dir):
  """Runs the site_diff."""
  coordinator = workers.GetCoordinator()
  coordinator.start()
  try:
    item = SiteDiff(url, ignore_prefixes, output_dir, reference_dir)
    coordinator.input_queue.put(item)
    result = coordinator.output_queue.get()
    if result.error:
      raise result.error[0], result.error[1], result.error[2]
  finally:
    coordinator.stop()


def main(argv):
  gflags.MarkFlagAsRequired('phantomjs_binary')
  gflags.MarkFlagAsRequired('phantomjs_script')
  gflags.MarkFlagAsRequired('pdiff_binary')
  gflags.MarkFlagAsRequired('output_dir')

  try:
    argv = FLAGS(argv)
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  logging.getLogger().setLevel(logging.DEBUG)
  real_main(
      argv[1], FLAGS.ignore_prefixes, FLAGS.output_dir, FLAGS.reference_dir)


if __name__ == '__main__':
  main(sys.argv)
