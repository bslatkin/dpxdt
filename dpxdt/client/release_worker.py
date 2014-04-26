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

"""Background worker that uploads new release candidates."""

import hashlib
import os

# Local Libraries
import gflags
FLAGS = gflags.FLAGS

# Local modules
from dpxdt.client import fetch_worker
from dpxdt.client import workers


gflags.DEFINE_string(
    'release_server_prefix', None,
    'URL prefix of where the release server is located, such as '
    '"https://www.example.com/here/is/my/api". This should use HTTPS if '
    'possible, since API requests send credentials using HTTP basic auth.')

gflags.DEFINE_string(
    'release_client_id', None,
    'Client ID of the API key to use for requests to the release server.')

gflags.DEFINE_string(
    'release_client_secret', None,
    'Client secret of the API key to use for requests to the release server.')


class Error(Exception):
    """Base-class for exceptions in this module."""

class CreateReleaseError(Error):
    """Creating a new release failed for some reason."""

class UploadFileError(Error):
    """Uploading a file failed for some reason."""

class FindRunError(Error):
    """Finding a run failed for some reason."""

class RequestRunError(Error):
    """Requesting a run failed for some reason."""

class ReportRunError(Error):
    """Reporting a run failed for some reason."""

class ReportPdiffError(Error):
    """Reporting a pdiff failed for some reason."""

class RunsDoneError(Error):
    """Marking that all runs are done failed for some reason."""

class DownloadArtifactError(Error):
    """Downloading an artifact failed for some reason."""


class StreamingSha1File(file):
    """File sub-class that sha1 hashes the data as it's read."""

    def __init__(self, *args, **kwargs):
        """Replacement for open()."""
        file.__init__(self, *args, **kwargs)
        self.sha1 = hashlib.sha1()

    def read(self, *args):
        data = file.read(self, *args)
        self.sha1.update(data)
        return data

    def close(self):
        file.close(self)

    def hexdigest(self):
        return self.sha1.hexdigest()


class CreateReleaseWorkflow(workers.WorkflowItem):
    """Creates a new release candidate.

    Args:
        build_id: ID of the build.
        release_name: Name of the release candidate.
        url: Landing URL of the new release.

    Returns:
        The newly created release_number.

    Raises:
        CreateReleaseError if the release could not be created.
    """

    def run(self, build_id, release_name, url):
        call = yield fetch_worker.FetchItem(
            FLAGS.release_server_prefix + '/create_release',
            post={
                'build_id': build_id,
                'release_name': release_name,
                'url': url,
            },
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise CreateReleaseError(call.json.get('error'))

        if not call.json or not call.json.get('release_number'):
            raise CreateReleaseError('Bad response: %r' % call)

        raise workers.Return(call.json['release_number'])


class UploadFileWorkflow(workers.WorkflowItem):
    """Uploads a file for a build.

    Args:
        build_id: ID of the build to upload a file for.
        file_path: Path to the file to upload.

    Returns:
        sha1 sum of the file's contents or None if the file could not
        be found.

    Raises:
        UploadFileError if the file could not be uploaded.
    """

    def run(self, build_id, file_path):
        try:
            handle = StreamingSha1File(file_path, 'rb')
            upload = yield fetch_worker.FetchItem(
                FLAGS.release_server_prefix + '/upload',
                post={'build_id': build_id, 'file': handle},
                timeout_seconds=120,
                username=FLAGS.release_client_id,
                password=FLAGS.release_client_secret)

            if upload.json and upload.json.get('error'):
                raise UploadFileError(upload.json.get('error'))

            sha1sum = handle.hexdigest()
            if not upload.json or upload.json.get('sha1sum') != sha1sum:
                raise UploadFileError('Bad response: %r' % upload)

            raise workers.Return(sha1sum)

        except IOError:
            raise workers.Return(None)


class FindRunWorkflow(workers.WorkflowItem):
    """Finds the last good run for a release.

    Args:
        build_id: ID of the build.
        run_name: Name of the run being uploaded.

    Returns:
        JSON dictionary representing the run that was found, with the keys:
        build_id, release_name, release_number, run_name, url, image, log,
        config.

    Raises:
        FindRunError if a run could not be found.
    """

    def run(self, build_id, run_name):
        call = yield fetch_worker.FetchItem(
            FLAGS.release_server_prefix + '/find_run',
            post={
                'build_id': build_id,
                'run_name': run_name,
            },
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise FindRunError(call.json.get('error'))

        if not call.json:
            raise FindRunError('Bad response: %r' % call)

        raise workers.Return(call.json)


class RequestRunWorkflow(workers.WorkflowItem):
    """Requests the API server to do a test run and capture the results.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Name of the run being requested.
        url: URL to fetch for the run.
        config_data: The JSON data that is the config for this run.
        ref_url: Optional. URL of the baseline to fetch for the run.
        ref_config_data: Optional. The JSON data that is the config for the
            baseline of this run.

    Raises:
        RequestRunError if the run could not be requested.
    """

    def run(self, build_id, release_name, release_number, run_name,
            url=None, config_data=None, ref_url=None, ref_config_data=None):
        post = {
            'build_id': build_id,
            'release_name': release_name,
            'release_number': release_number,
            'run_name': run_name,
            'url': url,
            'config': config_data,
        }
        if ref_url and ref_config_data:
            post.update(
                ref_url=ref_url,
                ref_config=ref_config_data)

        call = yield fetch_worker.FetchItem(
            FLAGS.release_server_prefix + '/request_run',
            post=post,
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise RequestRunError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise RequestRunError('Bad response: %r' % call)


class ReportRunWorkflow(workers.WorkflowItem):
    """Reports a run as finished.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Name of the run being uploaded.
        log_path: Optional. Path to the screenshot log to upload.
        image_path: Optional. Path to the screenshot to upload.
        url: Optional. URL that was fetched for the run.
        config_path: Optional. Path to the config to upload.
        ref_url: Optional. Previously fetched URL this is being compared to.
        ref_image: Optional. Asset ID of the image to compare to.
        ref_log: Optional. Asset ID of the reference image's log.
        ref_config: Optional. Asset ID of the reference image's config.
        baseline: Optional. When specified and True, the log_path, url,
            and image_path are for the reference baseline of the specified
            run, not the new capture. If this is True, the ref_* parameters
            must not be provided.
        run_failed: Optional. When specified and True it means that this run
            has failed for some reason. The run may be tried again in the
            future but this will cause this run to immediately show up as
            failing. When not specified or False the run will be assumed to
            have been successful.

    Raises:
        ReportRunError if the run could not be reported.
    """

    def run(self, build_id, release_name, release_number, run_name,
            image_path=None, log_path=None, url=None, config_path=None,
            ref_url=None, ref_image=None, ref_log=None, ref_config=None,
            baseline=None, run_failed=False):
        if baseline and (ref_url or ref_image or ref_log or ref_config):
            raise ReportRunError(
                'Cannot specify "baseline" along with any "ref_*" arguments.')

        upload_jobs = [
            UploadFileWorkflow(build_id, log_path),
        ]
        if image_path:
            image_index = len(upload_jobs)
            upload_jobs.append(UploadFileWorkflow(build_id, image_path))

        if config_path:
            config_index = len(upload_jobs)
            upload_jobs.append(UploadFileWorkflow(build_id, config_path))

        results = yield upload_jobs
        log_id = results[0]
        image_id = None
        config_id = None
        if image_path:
            image_id = results[image_index]
        if config_path:
            config_id = results[config_index]

        post = {
            'build_id': build_id,
            'release_name': release_name,
            'release_number': release_number,
            'run_name': run_name,
        }

        if baseline:
            ref_url = url
            ref_log = log_id
            ref_image = image_id
            ref_config = config_id
            url = None
            log_id = None
            image_id = None
            config_id = None

        if url:
            post.update(url=url)
        if image_id:
            post.update(image=image_id)
        if log_id:
            post.update(log=log_id)
        if config_id:
            post.update(config=config_id)

        if run_failed:
            post.update(run_failed='yes')

        if ref_url:
            post.update(ref_url=ref_url)
        if ref_image:
            post.update(ref_image=ref_image)
        if ref_log:
            post.update(ref_log=ref_log)
        if ref_config:
            post.update(ref_config=ref_config)

        call = yield fetch_worker.FetchItem(
            FLAGS.release_server_prefix + '/report_run',
            post=post,
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise ReportRunError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise ReportRunError('Bad response: %r' % call)


class ReportPdiffWorkflow(workers.WorkflowItem):
    """Reports a pdiff's result status.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.
        run_name: Name of the pdiff being uploaded.
        diff_path: Path to the diff to upload.
        log_path: Path to the diff log to upload.
        diff_failed: True when there was a problem computing the diff. False
            when the diff was computed successfully. Defaults to False.

    Raises:
        ReportPdiffError if the pdiff status could not be reported.
    """

    def run(self, build_id, release_name, release_number, run_name,
            diff_path=None, log_path=None, diff_failed=False, distortion=None):
        diff_id = None
        log_id = None
        if (isinstance(diff_path, basestring) and
                os.path.isfile(diff_path) and
                isinstance(log_path, basestring) and
                os.path.isfile(log_path)):
            diff_id, log_id = yield [
                UploadFileWorkflow(build_id, diff_path),
                UploadFileWorkflow(build_id, log_path),
            ]
        elif isinstance(log_path, basestring) and os.path.isfile(log_path):
            log_id = yield UploadFileWorkflow(build_id, log_path)

        post = {
            'build_id': build_id,
            'release_name': release_name,
            'release_number': release_number,
            'run_name': run_name,
        }
        if diff_id:
            post.update(diff_image=diff_id)
        if log_id:
            post.update(diff_log=log_id)
        if diff_failed:
            post.update(diff_failed='yes')
        if distortion:
            post.update(distortion=distortion)

        call = yield fetch_worker.FetchItem(
            FLAGS.release_server_prefix + '/report_run',
            post=post,
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise ReportPdiffError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise ReportPdiffError('Bad response: %r' % call)


class RunsDoneWorkflow(workers.WorkflowItem):
    """Reports all runs are done for a release candidate.

    Args:
        build_id: ID of the build.
        release_name: Name of the release.
        release_number: Number of the release candidate.

    Returns:
        URL of where the results for this release candidate can be viewed.

    Raises:
        RunsDoneError if the release candidate could not have its runs
        marked done.
    """

    def run(self, build_id, release_name, release_number):
        call = yield fetch_worker.FetchItem(
            FLAGS.release_server_prefix + '/runs_done',
            post={
                'build_id': build_id,
                'release_name': release_name,
                'release_number': release_number,
            },
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)

        if call.json and call.json.get('error'):
            raise RunsDoneError(call.json.get('error'))

        if not call.json or not call.json.get('success'):
            raise RunsDoneError('Bad response: %r' % call)

        raise workers.Return(call.json['results_url'])


class DownloadArtifactWorkflow(workers.WorkflowItem):
    """Downloads an artifact to a given path.

    Args:
        build_id: ID of the build.
        sha1sum: Content hash of the artifact to fetch.
        result_path: Path where the artifact should be saved on disk.

    Raises:
        DownloadArtifactError if the artifact could not be found or
        fetched for some reason.
    """

    def run(self, build_id, sha1sum, result_path):
        download_url = '%s/download?sha1sum=%s&build_id=%s' % (
            FLAGS.release_server_prefix, sha1sum, build_id)
        call = yield fetch_worker.FetchItem(
            download_url,
            result_path=result_path,
            username=FLAGS.release_client_id,
            password=FLAGS.release_client_secret)
        if call.status_code != 200:
            raise DownloadArtifactError('Bad response: %r' % call)
