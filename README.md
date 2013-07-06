# Depicted—dpxdt

Make continuous deployment safe by comparing before and after webpage screenshots for each release. Depicted shows when any visual, perceptual differences are found. This is the ultimate, automated end-to-end test.

**[View the test instance here](https://dpxdt-test.appspot.com)**

Depicted is:

- An API server for capturing webpage screenshots and automatically generating visual, perceptual difference images ("pdiffs").
- A workflow for teams to coordinate new releases using pdiffs.
- A client library for integrating with existing continuous integration processes.
- Built for portability; API server runs on App Engine, behind the firewall, etc.
- A wrapper of [PhantomJS](http://phantomjs.org/) for screenshots.
- Open source, Apache 2.0 licensed.
- Not a framework, not a religion.

**Depicted is not finished! [Please let us know if you have feedback or find bugs](https://github.com/bslatkin/dpxdt/issues/new).**

See [this video for a presentation](http://youtu.be/UMnZiTL0tUc) about how perceptual diffs have made continuous deployment safe.

## Overview

Here are the steps to making Depicted useful to you:

1. Establish a baseline release with an initial set of screenshots of your site.
1. Create a new release with a new set of screenshots of your new version.
1. Manually approve or reject each difference the tool finds.
1. Manually mark the new release as good or bad.
1. Repeat. Your approved release will become the baseline for the next one.

Depicted organizes your releases by a build ID. You can create a build through the API server's UI. A build is usually synonymous with a binary that's pushed to production. But it could also be a unique view into one product, like one build for desktop web and another for mobile web.

Within a build are releases with names. I recommend naming a release as the day it was branched in your source repository, and maybe an attempt number, like "06-16-r01" for June 16th, release 1. If you use codenames for your releases, like "bumblebee", that works too.

Each release may be attempted many times. The full history of each release attempt is saved in the UI. Releases can be manually marked as good or bad in the UI. When results for a new release are uploaded, they will automatically be compared to the last known-good version within that build.

A release consists of many separate test runs. A test run is a single screenshot of a single page. A test run has a name that is used to pair it up with a baseline test run from the known-good, previous release. Usually the test run is named as the path of the URL being tested (like /foo?bar=meep). This lets the baseline release and new release serve on different hostnames.

The life-cycle of a release:

1. Created: A new release is created with a specific name. The system gives it a release number.
1. Receiving: The release is waiting for all test runs to be requested or reported.
1. Processing: All test runs have been reported, but additional processing (like screenshotting or pdiffing) is required.
1. Reviewing: All test runs have been processed. Now the build admin should review any pdiffs that were found and approve the release.

Final release states:
- Bad: The build admin has marked the release and all its test runs as bad. It will never be used as a baseline.
- Good: The build admin has marked the release and all of its test runs as passing. The next release created for this build will use this just-approved release as the new baseline.

## Getting started

Depicted is written in portable Python. It uses Flask and SQLAlchemy to make it easy to run in your environment. It works with SQLite out of the box. The API server runs on App Engine. The workers run [ImageMagick](http://www.imagemagick.org/Usage/compare/) and [PhantomJS](http://phantomjs.org/) as subprocesses. I like to run the worker on a cloud VM, but you could run it on your laptop behind a firewall if that's important to you. See [deployment](#deployment) below for details.

### Running the server locally

1. Have a version of [Python 2.7](http://www.python.org/download/releases/2.7/) installed.
1. Download [PhantomJS](http://phantomjs.org/) for your machine.
1. Download [ImageMagick](http://www.imagemagick.org/script/binary-releases.php) for your machine.
1. Clone this git repo in your terminal:

        git clone https://github.com/bslatkin/dpxdt.git

1. ```cd``` to the repo directory:
1. Update all git submodules in the repo:

        git submodule update --init --recursive

1. Modify ```common.sh``` to match your enviornment:
        
        # Edit variables such as ...
        export PHANTOMJS_BINARY=/Users/yourname/Downloads/phantomjs-1.9.0-macosx/bin/phantomjs

1. Write a ```secrets.py``` file to the root directory:

        SECRET_KEY = 'insert random string of characters here'

1. Execute ```./run_shell.sh``` and run these commands to initialize your DB:

        server.db.drop_all()
        server.db.create_all()

1. Run the combined server/worker with ```./run_combined.sh```.
1. Navigate to [http://localhost:5000](http://localhost:5000).
1. Login and create a new build.
1. Execute the ```./run_url_pair_diff.sh``` tool to verify everything is working:

        ./run_url_pair_diff.sh \
            --upload_build_id=1 \
            http://www.google.com \
            http://www.yahoo.com

1. Follow the URL the tool writes to the terminal and verify screenshots are present. Any errors will be printed to the log in the terminal where you are running the server process.


### Other scripts

To run the "site diff" script, use:

```
./run_site_diff.sh \
    --upload_build_id=1 \
    --crawl_depth=1 \
    http://www.example.com
```

To run the tests to make sure you haven't broken the world:

```
./run_tests.sh
```

To run the API server locally, without any worker threads:

```
./run_server.sh
```

To run the background workers independently against the local API server:

```
./run_worker.sh
```

To run in the App Engine development environment (see the [section on deployment](#deployment) for config details):

```
./appengine_run.sh
```

## API

You can try out the API on the test instance of Depicted located at [https://dpxdt-test.appspot.com](https://dpxdt-test.appspot.com). This instance's database will be dropped from time to time, so please don't rely on it.

The API is really simple. All requests are POSTs with parameters that are URL encoded. All responses are JSON. All requests should be over HTTPS. The API server uses HTTP Basic Authentication to verify your client has access to your builds. You can provision API keys for a build on its homepage (at the bottom).

Here's an example request to the API server using curl. Pretty easy.

```
curl -v \
    -u api_key:api_password \
    -F build_id=1 \
    -F 'run_name=/static/dummy/dummy_page1.html' \
    -F 'release_number=1' \
    -F 'log=906d3259c103f6fcba4e8164a4dc3ae0d1a685d9' \
    -F 'release_name=2013-06-16 17:35:03.327710' \
    'http://localhost:5000/api/report_run'
```

### Example tools that use the API

An example client tool that exercises the whole workflow is [available in the repo](./dpxdt/tools/site_diff.py). It's called "Site Diff". It will crawl a webpage, follow all links with the same prefix path, then create a new release that screenshots all the URLs. Running the tool multiple times lets you diff your entire site with little effort. Site Diff is very helpful, for example, when you have a blog with a lot of content and want to make a change to your base template and be sure you haven't broken any pages.

Here's an example invocation of Site Diff:

```
./dpxdt/tools/site_diff.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    --crawl_depth=1 \
    http://www.example.com/my/website/here
```

Another example tool is [available in the repo](./dpxdt/tools/url_pair_diff.py) called Pair Diff. Unlike Site Diff, which establishes a baseline on each subsequent run, Pair Diff takes two live URLs and compares them. This is useful when you have a live version and staging version of your site both available at the same time and can do screenshots of both independently.

Here's an example run of Pair Diff:

```
./dpxdt/tools/url_pair_diff.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    http://www.example.com/my/before/page \
    http://www.example.com/my/after/page
```

### API Reference

All of these requests are POSTs with URL-encoded or multipart/form-data bodies and require HTTP Basic Authentication using your API key as the username and secret as the password. All responses are JSON. The 'success' key will be present in all responses and true if the request was successful. If 'success' isn't present, a human-readable error message may be present in the response under the key 'error'.

#### /api/create_release

Creates a new release candidate for a build.

##### Parameters
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the new release.</dd>
    <dt>url</dt>
    <dd>URL of the homepage of the new release. Only present for humans who need to understand what a release is for.</dd>
</dl>

##### Returns
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the release that was just created.</dd>
    <dt>release_number</dt>
    <dd>Number assigned to the new release by the system.</dd>
    <dt>url</dt>
    <dd>URL of the release's homepage.</dd>
</dl>

#### /api/find_run

Finds the last good run of the given name for a release. Returns an error if no run previous good release exists.

##### Parameters
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>run_name</dt>
    <dd>Name of the run to find the last known-good version of.</dd>
</dl>

##### Returns
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the last known-good release for the run.</dd>
    <dt>release_number</dt>
    <dd>Number of the last known-good release for the run.</dd>
    <dt>run_name</dt>
    <dd>Name of the run that was found. May be null if a run could not be found.</dd>
    <dt>url</dt>
    <dd>URL of the last known-good release for the run. May be null if a run could not be found.</dd>
    <dt>image</dt>
    <dd>Artifact ID (SHA1 hash) of the screenshot image associated with the run. May be null if a run could not be found.</dd>
    <dt>log</dt>
    <dd>Artifact ID (SHA1 hash) of the log file from the screenshot process associated with the run. May be null if a run could not be found.</dd>
    <dt>config</dt>
    <dd>Artifact ID (SHA1 hash) of the config file used for the screenshot process associated with the run. May be null if a run could not be found.</dd>
</dl>

#### /api/request_run

Requests a new run for a release candidate. Causes the API system to take screenshots and do pdiffs. When `ref_url` and `ref_config` are supplied, the system will run two sets of captures (one for the baseline, one for the new release) and then compare them. When `rel_url` and `ref_config` are not specified, the last good run for this build is found and used for comparison.

##### Parameters
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the release.</dd>
    <dt>release_number</dt>
    <dd>Number of the release.</dd>
    <dt>url</dt>
    <dd>URL to request as a run.</dd>
    <dt>config</dt>
    <dd>JSON data that is the config for the new run.</dd>
    <dt>ref_url</dt>
    <dd>URL of the baseline to request as a run.</dd>
    <dt>ref_config</dt>
    <dd>JSON data that is the config for the baseline of the new run.</dd>
</dl>

###### Format of `config`

The config passed to the `request_run` function may have any or all of these fields. All fields are optional and have reasonably sane defaults.

```json
{
    "viewportSize": {
        "width": 1024,
        "height": 768
    },
    "injectCss": ".my-css-rules-here { display: none; }",
    "injectJs": "document.getElementById('foobar').innerText = 'foo';"
}
```

##### Returns
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the release.</dd>
    <dt>release_number</dt>
    <dd>Number of the release.</dd>
    <dt>run_name</dt>
    <dd>Name of the run that was created.</dd>
    <dt>url</dt>
    <dd>URL that was requested for the run.</dd>
    <dt>config</dt>
    <dd>Artifact ID (SHA1 hash) of the config file that will be used for the screenshot process associated with the run.</dd>
    <dt>ref_url</dt>
    <dd>URL that was requested for the baseline reference for the run.</dd>
    <dt>ref_config</dt>
    <dd>Artifact ID (SHA1 hash) of the config file used for the baseline screenshot process of the run.</dd>
</dl>

#### /api/upload

Uploads an artifact referenced by a run.

##### Parameters
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>(a single file in the multipart/form-data)</dt>
    <dd>Data of the file being uploaded. Should have a filename in the mime headers so the system can infer the content type of the uploaded asset.</dd>
</dl>

##### Returns
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>sha1sum</dt>
    <dd>Artifact ID (SHA1 hash) of the file that was uploaded.</dd>
    <dt>content_type</dt>
    <dd>Content type of the artifact that was uploaded.</dd>
</dl>

#### /api/report_run

Reports data for a run for a release candidate. May be called multiple times as progress is made for a run. No longer callable once the screenshot image for the run has been assigned.

##### Parameters
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the release.</dd>
    <dt>release_number</dt>
    <dd>Number of the release.</dd>
    <dt>run_name</dt>
    <dd>Name of the run.</dd>
    <dt>url</dt>
    <dd>URL associated with the run.</dd>
    <dt>image</dt>
    <dd>Artifact ID (SHA1 hash) of the screenshot image associated with the run.</dd>
    <dt>log</dt>
    <dd>Artifact ID (SHA1 hash) of the log file from the screenshot process associated with the run.</dd>
    <dt>config</dt>
    <dd>Artifact ID (SHA1 hash) of the config file used for the screenshot process associated with the run.</dd>
    <dt>ref_url</dt>
    <dd>URL associated with the run's baseline release.</dd>
    <dt>ref_image</dt>
    <dd>Artifact ID (SHA1 hash) of the screenshot image associated with the run's baseline release.</dd>
    <dt>ref_log</dt>
    <dd>Artifact ID (SHA1 hash) of the log file from the screenshot process associated with the run's baseline release.</dd>
    <dt>ref_config</dt>
    <dd>Artifact ID (SHA1 hash) of the config file used for the screenshot process associated with the run's baseline release.</dd>
    <dt>diff_image</dt>
    <dd>Artifact ID (SHA1 hash) of the perceptual diff image associated with the run.</dd>
    <dt>diff_log</dt>
    <dd>Artifact ID (SHA1 hash) of the log file from the perceptual diff process associated with the run.</dd>
    <dt>diff_success</dt>
    <dd>Present and non-empty string when the diff process ran successfully. May be missing when diff ran and reported a log but may need to retry for this run.</dd>
</dl>

##### Returns
Nothing but success on success.

#### /api/runs_done

Marks a release candidate as having all runs reported.

##### Parameters
<dl>
    <dt>build_id</dt>
    <dd>ID of the build.</dd>
    <dt>release_name</dt>
    <dd>Name of the release.</dd>
    <dt>release_number</dt>
    <dd>Number of the release.</dd>
</dl>

##### Returns
<dl>
    <dt>results_url</dt>
    <dd>URL where a release candidates run status can be viewed in a web browser by a build admin.</dd>
</dl>

## Deployment

This is still kinda rough. It primarily explains how to deploy to App Engine / CloudSQL / Google Compute Engine.

1. Provision a CloudSQL DB for your project and initialize it:

        ./google_sql.sh dpxdt-cloud:test
        sql> create database test;

1. Go to the [Google API console](https://code.google.com/apis/console/) and provision a new project and "API Access". This will give you the OAuth client ID and secret you need to make auth work properly. Update ```config.py``` with your values.
1. Go to the [Google Cloud Console](cloud.google.com/console) and find the Google Cloud Storage bucket you've created for your deployment. In the App Engine admin console, go to "Application Settings" and find your "Service Account Name". Copy that name and in the Cloud Console add it as a team member (this gives your app access to the bucket). Update ```config.py``` with your bucket.
1. Go to the ```deployment/appengine``` directory. Update ```app.yaml``` with your parameters. Create the ```secrets.py``` file as explained for development.
1. Deploy the app:

        ./appengine_deploy.sh

1. Navigate to ```/admin``` on your app and run in the interactive console:

        from dpxdt import server
        server.db.create_all()

1. Navigate to ```/``` on your app and see the homepage. Create a new build. Provision an API key. Then set your user and API key as superusers using the SQL tool:

        select * from user;
        update user set superuser = 1 where user.id = 'foo';
        select * from api_key;
        update api_key set superuser = 1 where id = 'foo';

1. Now create the background workers package to deploy:

        ./worker_deploy.sh

1. Follow the commands it prints out to deploy the worker to a VM.
