#!/usr/bin/env python
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility for doing incremental diffs for a live website.

TODO: Move these examples to the readme

Example local usage:

./site_diff.py \
    --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
    --phantomjs_script=path/to/client/capture.js \
    --pdiff_binary=path/to/pdiff/perceptualdiff \
    --output_dir=path/to/your/output \
    http://www.example.com/my/website/here


Example usage with API server:

./site_diff.py \
    --phantomjs_binary=path/to/phantomjs-1.8.1-macosx/bin/phantomjs \
    --phantomjs_script=path/to/client/capture.js \
    --pdiff_binary=path/to/pdiff/perceptualdiff \
    --output_dir=path/to/your/output \
    --upload_build_id=1234 \
    http://www.example.com/my/website/here

"""

import HTMLParser
import Queue
import datetime
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import urlparse

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
import capture_worker
import dpxdt
import pdiff_worker
import release_worker
import workers


gflags.DEFINE_integer(
    'crawl_depth', -1,
    'How deep to crawl. Depth of 0 means only the given page. 1 means pages '
    'that are one click away, 2 means two clicks, and so on. Set to -1 to '
    'scan every URL with the supplied prefix.')

gflags.DEFINE_spaceseplist(
    'ignore_prefixes', [],
    'URL prefixes that should not be crawled.')

gflags.DEFINE_string(
    'output_dir', None,
    'Directory where the output should be saved. If it does not exist '
    'it will be created.')

gflags.DEFINE_string(
    'reference_dir', None,
    'Directory where this tool last ran; used for generating new diffs. '
    'When empty, no diffs will be made.')

gflags.DEFINE_string(
    'upload_build_id', None,
    'ID of the build to upload this screenshot set to as a new release.')

gflags.DEFINE_string(
    'upload_release_name', None,
    'Along with upload_build_id, the name of the release to upload to.')


class Error(Exception):
    """Base class for exceptions in this module."""

class CaptureFailedError(Error):
    """Capturing a page screenshot failed."""


# URL regex rewriting code originally from mirrorrr
# http://code.google.com/p/mirrorrr/source/browse/trunk/transform_content.py

# URLs that have absolute addresses
ABSOLUTE_URL_REGEX = r"(?P<url>(http(s?):)?//[^\"'> \t]+)"
# URLs that are relative to the base of the current hostname.
BASE_RELATIVE_URL_REGEX = (
    r"/(?!(/)|(http(s?)://)|(url\())(?P<url>[^\"'> \t]*)")
# URLs that have '../' or './' to start off their paths.
TRAVERSAL_URL_REGEX = (
    r"(?P<relative>\.(\.)?)/(?!(/)|"
    r"(http(s?)://)|(url\())(?P<url>[^\"'> \t]*)")
# URLs that are in the same directory as the requested URL.
SAME_DIR_URL_REGEX = r"(?!(/)|(http(s?)://)|(#)|(url\())(?P<url>[^\"'> \t]+)"
# URL matches the root directory.
ROOT_DIR_URL_REGEX = r"(?!//(?!>))/(?P<url>)(?=[ \t\n]*[\"'> /])"
# Start of a tag using 'src' or 'href'
TAG_START = (
    r"(?i)(?P<tag>\ssrc|href|action|url|background)"
    r"(?P<equals>[\t ]*=[\t ]*)(?P<quote>[\"']?)")
# Potential HTML document URL with no fragments.
MAYBE_HTML_URL_REGEX = (
    TAG_START + r"(?P<absurl>(http(s?):)?//[^\"'> \t]+)")

REPLACEMENT_REGEXES = [
    (TAG_START + SAME_DIR_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(accessed_dir)s\g<url>"),
    (TAG_START + TRAVERSAL_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(accessed_dir)s/\g<relative>/\g<url>"),
    (TAG_START + BASE_RELATIVE_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(base)s/\g<url>"),
    (TAG_START + ROOT_DIR_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>%(base)s/"),
    (TAG_START + ABSOLUTE_URL_REGEX,
     "\g<tag>\g<equals>\g<quote>\g<url>"),
]


def clean_url(url, force_scheme=None):
    """Cleans the given URL."""
    # Collapse ../../ and related
    url_parts = urlparse.urlparse(url)
    path_parts = []
    for part in url_parts.path.split('/'):
        if part == '.':
            continue
        elif part == '..':
            if path_parts:
                path_parts.pop()
        else:
            path_parts.append(part)

    url_parts = list(url_parts)
    if force_scheme:
        url_parts[0] = force_scheme
    url_parts[2] = '/'.join(path_parts)
    url_parts[4] = ''    # No query string
    url_parts[5] = ''    # No path

    # Always have a trailing slash
    if not url_parts[2]:
        url_parts[2] = '/'

    return urlparse.urlunparse(url_parts)


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
        found_url = clean_url(
            found_url,
            force_scheme=parts[0])  # Use the main page's scheme
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

    def run(self, url, output_dir, reference_dir, heartbeat=None):
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

        capture = yield capture_worker.CaptureItem(
            output_base + '_run.txt',
            config_path,
            output_base + '_run.png')

        if capture.returncode != 0:
            raise CaptureFailedError('Failed to capture url=%r' % url)

        yield heartbeat('Captured: %s' % url)

        if not reference_dir:
            raise workers.Return((
                parts.path, url, capture.output_path, capture.log_path,
                capture.config_path))

        ref_base = os.path.join(reference_dir, clean_url)
        last_run = ref_base + '_run.png'
        if not os.path.exists(last_run):
            return

        last_log = ref_base + '_run.txt'
        if not os.path.exists(last_log):
            return

        ref_output = output_base + '_ref.png'
        ref_log = output_base + '_ref.txt'
        shutil.copy(last_run, ref_output)
        shutil.copy(last_log, ref_log)

        diff_output = output_base + '_diff.png'
        diff = yield pdiff_worker.PdiffItem(
            output_base + '_diff.txt',
            ref_output,
            capture.output_path,
            diff_output)

        yield heartbeat('Diffed: %s' % url)

        if diff.returncode != 0 and os.path.exists(diff_output):
            yield heartbeat('Found diff for path=%r, diff=%r' %
                            (parts.path, diff_output))


class SiteDiff(workers.WorkflowItem):
    """Workflow for coordinating the site diff.

    Args:
        start_url: URL to begin the site diff scan.
        output_dir: Directory path where the results should be saved.
        ignore_prefixes: Optional. List of URL prefixes to ignore during
            the crawl; start_url should be a common prefix with all of these.
        reference_dir: Optional, mutually exclusive with upload_build_id.
            Directory of a previous run of this workflow with images to
            compare this one to.
        upload_build_id: Optional. Build ID of the site being compared. When
            supplied a new release will be cut for this build comparing it
            to the last good release.
        upload_release_name: Optional. Release name to use for the build. When
            not supplied, a new release based on the current time will be
            created.
        heartbeat: Function to call with progress status.
    """

    def run(self,
            start_url,
            output_dir,
            ignore_prefixes,
            reference_dir=None,
            upload_build_id=None,
            upload_release_name=None,
            heartbeat=None):
        assert not upload_build_id or (upload_build_id and not reference_dir)

        if not ignore_prefixes:
            ignore_prefixes = []

        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)

        pending_urls = set([clean_url(start_url)])
        seen_urls = set()
        good_urls = set()

        yield heartbeat('Scanning for content')

        limit_depth = FLAGS.crawl_depth >= 0
        depth = 0
        while (not limit_depth or depth <= FLAGS.crawl_depth) and pending_urls:
            # TODO: Enforce a job-wide timeout on the whole process of
            # URL discovery, to make sure infinitely deep sites do not
            # cause this job to never stop.
            seen_urls.update(pending_urls)
            output = yield [workers.FetchItem(u) for u in pending_urls]
            pending_urls.clear()

            for item in output:
                if not item.data:
                    logging.debug('No data from url=%r', item.url)
                    continue

                if item.headers.gettype() != 'text/html':
                    logging.debug('Skipping non-HTML document url=%r',
                                  item.url)
                    continue

                good_urls.add(item.url)
                found = extract_urls(item.url, item.data)
                pruned = prune_urls(
                    found, start_url, [start_url], ignore_prefixes)
                new = pruned - seen_urls
                pending_urls.update(new)
                yield heartbeat('Found %d new URLs from %s' % (
                                len(new), item.url))

            yield heartbeat('Finished crawl at depth %d' % depth)
            depth += 1

        yield heartbeat(
            'Found %d total URLs, %d good HTML pages; starting '
            'screenshots' % (len(seen_urls), len(good_urls)))

        if upload_build_id:
            # TODO: Make the default release name prettier.
            if not upload_release_name:
                upload_release_name = str(datetime.datetime.utcnow())
            release_number = yield release_worker.CreateReleaseWorkflow(
                upload_build_id, upload_release_name, start_url)

        found_urls = os.path.join(output_dir, 'url_paths.txt')
        good_paths = set(urlparse.urlparse(u).path for u in good_urls)
        with open(found_urls, 'w') as urls_file:
            urls_file.write('\n'.join(sorted(good_paths)))

        results = []
        for url in good_urls:
            results.append(PdiffWorkflow(url, output_dir, reference_dir,
                                         heartbeat=heartbeat))
        results = yield results

        if upload_build_id:
            # TODO: Parallelize this work with a sub-task
            for pdiff_result in results:
                (run_name, url, output_path, log_path, config_path
                    ) = pdiff_result
                yield heartbeat('Finding last good run for %s' %
                                run_name)
                ref_url, ref_image, ref_log, ref_config = (
                    None, None, None, None)
                try:
                    ref_run_result = yield release_worker.FindRunWorkflow(
                        upload_build_id, run_name)
                except release_worker.FindRunError:
                    yield heartbeat('Failed to find last good run for %s' %
                                    run_name)
                else:
                    ref_url = ref_run_result.get('url')
                    ref_image = ref_run_result.get('image')
                    ref_log = ref_run_result.get('log')
                    ref_config = ref_run_result.get('config')

                yield heartbeat('Uploading captured screenshots for %s' %
                                run_name)

                no_diff_needed = False
                if not ref_image:
                    no_diff_needed = True

                yield release_worker.ReportRunWorkflow(
                    upload_build_id,
                    upload_release_name,
                    release_number,
                    run_name,
                    url,
                    output_path,
                    log_path,
                    config_path,
                    ref_url=ref_url,
                    ref_image=ref_image,
                    ref_log=ref_log,
                    ref_config=ref_config,
                    no_diff_needed=no_diff_needed)

            yield heartbeat('Marking runs as complete')
            release_url = yield release_worker.RunsDoneWorkflow(
                upload_build_id, upload_release_name, release_number)

            yield heartbeat('Results will be at: %s' % release_url)
        else:
            yield heartbeat('Results in %s' % output_dir)


class PrintWorkflow(workers.WorkflowItem):
    """Prints a message to stdout."""

    def run(self, message):
        yield []  # Make this into a generator
        print message


def real_main(start_url=None,
              output_dir=None,
              ignore_prefixes=None,
              reference_dir=None,
              upload_build_id=None,
              upload_release_name=None,
              coordinator=None):
    """Runs the site_diff."""
    if not coordinator:
        coordinator = workers.GetCoordinator()
    capture_worker.register(coordinator)
    pdiff_worker.register(coordinator)
    coordinator.start()

    try:
        item = SiteDiff(
            start_url=start_url,
            output_dir=output_dir,
            ignore_prefixes=ignore_prefixes,
            reference_dir=reference_dir,
            upload_build_id=upload_build_id,
            upload_release_name=upload_release_name,
            heartbeat=PrintWorkflow)
        item.root = True
        coordinator.input_queue.put(item)
        result = coordinator.output_queue.get()
        result.check_result()
    finally:
        coordinator.stop()


def main(argv):
    gflags.MarkFlagAsRequired('phantomjs_binary')
    gflags.MarkFlagAsRequired('phantomjs_script')
    gflags.MarkFlagAsRequired('pdiff_binary')
    # If upload_build_id is set, then require release_server_prefix

    try:
        argv = FLAGS(argv)
    except gflags.FlagsError, e:
        print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
        sys.exit(1)

    if len(argv) != 2:
        print 'Must supply a website URL as the first argument.'
        sys.exit(1)

    if FLAGS.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    output_dir = FLAGS.output_dir
    if not output_dir:
        output_dir = tempfile.mkdtemp()

    real_main(
        start_url=argv[1],
        output_dir=output_dir,
        reference_dir=FLAGS.reference_dir,
        ignore_prefixes=FLAGS.ignore_prefixes,
        upload_build_id=FLAGS.upload_build_id,
        upload_release_name=FLAGS.upload_release_name)


if __name__ == '__main__':
    main(sys.argv)
