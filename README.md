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

[![Build Status](https://travis-ci.org/bslatkin/dpxdt.svg?branch=master)](https://travis-ci.org/bslatkin/dpxdt)

## Getting started

Depicted can be used in two ways: as a local tool for generating screenshots and as a server for coordinating continuous deployment.

To get started with either, run:

    pip install dpxdt

For the local tool, read on. For the server, [scroll on](#server).

## <a name="client"></a>Local Depicted

Local `dpxdt` is a tool for generating screenshots. It reads in a YAML config file and generates screenshots using PhantomJS. This makes sense for testing reusable tools (e.g. libraries) which aren't "deployed" in the way that a traditional web app is.

Create a simple page to screenshot:

```html
<!-- demo.html -->
<h2>dpxdt local demo</h2>
<p>dpxdt can be used to spot changes on local web servers.</p>
```

And a config file to specify what to screenshot:
```yaml
# (tests/test.yaml)
# This is run once before any individual test.
# It's a good place to start your demo server.
setup: |
    python -m SimpleHTTPServer

# This runs after the setup script and before any tests are run.
# It's a great place to wait for server startup.
waitFor:
    url: http://localhost:8000/demo.html
    timeout_secs: 5

tests:
  - name: demo
    url: http://localhost:8000/demo.html
    config: {}
```

The `setup` stanza is a bash script which typically starts the server you want to screenshot. Note that this script doesn't terminate—dpxdt will kill it when it's done.

The `waitFor` stanza tells dpxdt how it will know whether the server is ready for screenshotting. This stanza can be a bash script as well, but typically it suffices to specify a URL and a timeout. dpxdt will repeatedly fetch the URL until it resolves (i.e. returns status code 200).

The `tests` section specifies a list of URLs to fetch. The `name` value identifies the test and is also used as the output file name.

You can run this simple test via `dpxdt update tests`. Here's what it looks like:

    $ dpxdt update tests
    Request for http://localhost:8000/demo.html succeeded, continuing with tests...
    demo: Running webpage capture process
    demo: Updated tests/demo.png

This looks for YAML files in the `tests` directory and processes each in turn. It starts the `SimpleHTTPServer`, captures a screenshot and writes it to `tests/demo.png`:

![A screenshot of the demo page.](http://cl.ly/image/3F0K1B1P2b3V/demo.png)

To learn more about local dpxdt, check out its [tutorial](/LOCAL.md).

## <a name="server"></a>Depicted Server

Depicted is written in portable Python. It uses Flask and SQLAlchemy to make it easy to run in your environment. It works with SQLite out of the box right on your laptop. The API server can also run on App Engine. The workers run [ImageMagick](http://www.imagemagick.org/Usage/compare/) and [PhantomJS](http://phantomjs.org/) as subprocesses. I like to run the worker on a cloud VM, but you could run it on your behind a firewall if that's important to you. See [deployment](#deployment) below for details.

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

## How to use Depicted effectively

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


## Example tools

Here are some example tools that show you how to use Depicted and its API, which is [documented in detail](#api) below.

- [Site Diff](#site-diff)
- [Pair Diff](#pair-diff)
- [Diff My Images](#diff-my-images)
- [Diff My URLs](#diff-my-urls)

### Site Diff

An example client tool that exercises the whole workflow is [available in the repo](./dpxdt/tools/site_diff.py). It's called "Site Diff". It will crawl a webpage, follow all links with the same prefix path, then create a new release that screenshots all the URLs. Running the tool multiple times lets you diff your entire site with little effort. Site Diff is very helpful, for example, when you have a blog with a lot of content and want to make a change to your base template and be sure you haven't broken any pages.

Here's an example invocation of Site Diff for your local server:

```
./run_site_diff.sh \
    --upload_build_id=1 \
    --crawl_depth=1 \
    http://www.example.com/my/website/here
```

Here's an example invocation of Site Diff against a real API server:

```
./dpxdt/tools/site_diff.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    --crawl_depth=1 \
    http://www.example.com/my/website/here
```

Note, when you use this the "upload_build_id" above should be changed to match your build id in the UI, for example:
```
https://dpxdt-test.appspot.com/build?id=500
```
You should use:
```
--upload_build_id=500
```

### Pair Diff

Another example tool is [available in the repo](./dpxdt/tools/url_pair_diff.py) called Pair Diff. Unlike Site Diff, which establishes a baseline on each subsequent run, Pair Diff takes two live URLs and compares them. This is useful when you have a live version and staging version of your site both available at the same time and can do screenshots of both independently.

Here's an example run of Pair Diff for your local server:

```
./run_url_pair_diff.sh \
    --upload_build_id=1 \
    http://www.example.com/my/before/page \
    http://www.example.com/my/after/page
```

Here's an example run of Pair Diff against a real API server:

```
./dpxdt/tools/url_pair_diff.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    http://www.example.com/my/before/page \
    http://www.example.com/my/after/page
```

### Diff My Images

One more example tool is [available in the repo](./dpxdt/tools/diff_my_images.py) called Diff My Images. This client plugs screenshots generated in a tool like Selenium into Depicted. It uses the last known good screenshots for tests with the same name as the baseline for comparison. Depicted will generate diffs for you and manage the workflow.

To try this out on your local server, first establish a baseline:

```
./run_diff_my_images.sh \
    --upload_build_id=1 \
    --release_cut_url=http://example.com/my/release/branch \
    --tests_json_path=tests/testdata/my_tests.json \
    --upload_release_name="Awesome"
```

Go to [the release page](http://localhost:5000/release?number=1&id=1&name=Awesome) and mark the release as good. Then upload a new set of images that represents an update:

```
./run_diff_my_images.sh \
    --upload_build_id=1 \
    --release_cut_url=http://example.com/my/release/branch \
    --tests_json_path=tests/testdata/my_tests2.json \
    --upload_release_name="Awesome"
```

Go to [the release page](http://localhost:5000/release?number=2&id=1&name=Awesome) and wait for the diffs to generate. Note how the first set of images you uploaded are used as the baseline automatically.

This example app works by reading a config file like this:

```
[
    {
        "name": "My homepage",
        "run_failed": false,
        "image_path": "tests/testdata/JellyBean1920.png",
        "log_path": "tests/testdata/testlog1.txt",
        "url": "http://example.com/another/url/that/is/here"
    },
    {
        "name": "My other page",
        "run_failed": false,
        "image_path": "tests/testdata/JellyBellyBeans.png",
        "log_path": "/tmp/testlog2.txt",
        "url": "http://example.com/other/url/that/is/here"
    }
]
```

[See the source code](./dpxdt/tools/diff_my_images.py) for more details.

### Diff My URLs

Yet another example tool is [available in the repo](./dpxdt/tools/diff_my_urls.py) called Diff My URLs. This client runs a diff on a set of URLs that are provided in a config file. It makes it very easy to only test the URLs you care about in a way that can be checked into source control and updated. Currently the tool consumes JSON and assumes that JSON data would be generated by another script or from a more concise representation like YAML.

To try this out on your local server do:

```
./run_diff_my_urls.sh \
    --upload_build_id=1 \
    --upload_release_name="My release name" \
    --release_cut_url=http://example.com/path/to/my/release/tool/for/this/cut
    --tests_json_path=tests/testdata/my_url_tests.json
```

This example app works by reading a config file like this:

```
[
    {
        "name": "My homepage",
        "run_url": "http://localhost:5000/static/dummy/dummy_page1.html",
        "run_config": {
            "viewportSize": {
                "width": 1024,
                "height": 768
            },
            "injectCss": "#foobar { background-color: lime",
            "injectJs": "document.getElementById('foobar').innerText = 'bar';",
        },
        "ref_url": "http://localhost:5000/static/dummy/dummy_page1.html",
        "ref_config": {
            "viewportSize": {
                "width": 1024,
                "height": 768
            },
            "injectCss": "#foobar { background-color: goldenrod; }",
            "injectJs": "document.getElementById('foobar').innerText = 'foo';",
        }
    }
]
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

### API Reference

All of these requests are POSTs with URL-encoded or multipart/form-data bodies and require HTTP Basic Authentication using your API key as the username and secret as the password. All responses are JSON. The 'success' key will be present in all responses and true if the request was successful. If 'success' isn't present, a human-readable error message may be present in the response under the key 'error'.

Endpoints:

- [/api/create_release](#apicreate_release)
- [/api/find_run](#apifind_run)
- [/api/request_run](#apirequest_run)
- [/api/upload](#apiupload)
- [/api/report_run](#apireport_run)
- [/api/runs_done](#apiruns_done)

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
    "injectJs": "document.getElementById('foobar').innerText = 'foo';",
    "resourceTimeoutMs": 60000
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

Reports data for a run for a release candidate. May be called multiple times as progress is made for a run. Should not be called once the screenshot image for the run has been assigned.

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
    <dt>diff_failed</dt>
    <dd>Present and non-empty string when the diff process failed for some reason. May be missing when diff ran and reported a log but may need to retry for this run.</dd>
    <dt>run_failed</dt>
    <dd>Present and non-empty string when the run failed for some reason. May be missing when capture ran and reported a log but may need to retry for this run.</dd>
    <dt>distortion</dt>
    <dd>Float amount of difference found in the diff that was uploaded, as a float between 0 and 1</dd>
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

Here's how to deploy to App Engine / CloudSQL / Google Compute Engine. This guide is still a little rough.

1. [Create a new Cloud Project](http://cloud.google.com/console). Provision a CloudSQL DB and initialize it:

        ./google_sql.sh <your-project>:<your-db-name>
        sql> create database test;

1. Go to the [Google API console](https://code.google.com/apis/console/) and provision a new project and "API Access". This will give you the OAuth client ID and secret you need to make auth work properly. Update ```config.py``` with your values for anything with the prefix ```GOOGLE_OAUTH2_```.

1. Go to the [Google Cloud Console](http://cloud.google.com/console) and find the Google Cloud Storage bucket you've created for your deployment. In the App Engine admin console, go to "Application Settings" and find your "Service Account Name". Copy that name and in the Cloud Console add it as a team member (this gives your app access to the bucket). Update ```config.py``` with your bucket in ```GOOGLE_CLOUD_STORAGE_BUCKET```.

1. Go to the ```deployment/appengine``` directory. Update ```app.yaml``` with your parameters. Create the ```secrets.py``` file as explained for development. Edit ```config.py``` and change this to match your CloudSQL setup:

        SQLALCHEMY_DATABASE_URI = 'mysql+gaerdbms:///test?instance=<your-project>:<your-db-name>''

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

#### Upgrading production and migrating your database

Depicted uses [Alembic](https://alembic.readthedocs.org/en/latest/tutorial.html) to migrate production data stored in MySQL. The state of *your* database will be unique to when you last pulled from HEAD.

To update to the latest version of the DB schema, follow these steps:

1. Get an IP address assigned for your Google Cloud SQL database [following these directions](https://developers.google.com/cloud-sql/docs/access-control#appaccess). Set the root password for your account. Enable your development machine's IP to access your MySQL instance. You can test this is working by doing:

        mysql -h <your-instance-ip> -u root -p
        use <your-db-name>;
        show tables;
And you should see something like:

        +--------------------+
        | Tables_in_test     |
        +--------------------+
        | admin_log          |
        | alembic_version    |
        | api_key            |
        | artifact           |
        | artifact_ownership |
        | build              |
        | build_ownership    |
        | release            |
        | run                |
        | user               |
        | work_queue         |
        +--------------------+


1. Modify ```config.py``` to use a standard MySQL driver:

        SQLALCHEMY_DATABASE_URI = (
            'mysql+mysqldb://root:<your-password>@<your-instance-ip>/<your-db-name>')

1. Edit ```alembic.ini``` and set this value to match ```config.py```:

        sqlalchemy.url = mysql+mysqldb://root:<your-password>@<your-instance-ip>/<your-db-name>

1. Run alembic to generate a migration script:

        ./alembic.py revision --autogenerate -m 'production diff'
You'll get output that looks like this:

        INFO  [alembic.migration] Context impl MySQLImpl.
        INFO  [alembic.migration] Will assume non-transactional DDL.
        INFO  [alembic.autogenerate.compare] Detected removed table u'api_key_ownership'
        INFO  [alembic.autogenerate.compare] Detected NOT NULL on column 'admin_log.log_type'
        INFO  [alembic.autogenerate.compare] Detected added column 'run.distortion'
        INFO  [alembic.autogenerate.compare] Detected removed column 'work_queue.live'
        INFO  [alembic.autogenerate.compare] Detected NOT NULL on column 'work_queue.status'
          Generating /Users/bslatkin/projects/dpxdt/alembic/versions/160c55b1c4b9_production_diff.py ... done


1. Look inside the ```alembic/versions/<random_string>_production_diff.py``` file generated by Alembic and make sure it seems sane. Commit this to your git repo if you want to make the migration repeatable on multiple DB instances or downgradable so you can rollback.

1. Run the migration. This is scary! 

        ./alembic.py upgrade head
It will print this out and then sit there for a long time:

        INFO  [alembic.migration] Context impl MySQLImpl.
        INFO  [alembic.migration] Will assume non-transactional DDL.
        INFO  [alembic.migration] Running upgrade None -> 160c55b1c4b9, production diff
To find out what it's actually doing while it's running, reconnect using ```mysql``` as described above and run this command periodically:

        show processlist;
You'll see what is happening and how long it's taking:

        +----+------+----------------+------+---------+------+-------------------+---------------------------------------------+
        | Id | User | Host           | db   | Command | Time | State             | Info                                        |
        +----+------+----------------+------+---------+------+-------------------+---------------------------------------------+
        | 83 | root |                | test | Query   |  236 | copy to tmp table | ALTER TABLE run ADD COLUMN distortion FLOAT |
        | 87 | root |                | test | Query   |    0 | NULL              | show processlist                            |
        +----+------+----------------+------+---------+------+-------------------+---------------------------------------------+
Eventually the command will finish and drop you back at a shell.

1. Go back to the [Google Cloud Console](http://cloud.google.com/console) and disable the IP address for your MySQL instance. This is safer for your data. Google also charges you to have a public IP address and this stops the cost. You can reenable the IP address next time you need to migrate.

1. Update ```app.yaml``` with a new version name and run this command to deploy the new code on a new non-default version:

        ./appengine_deploy.sh

1. Access the new non-default version on a url like ```https://yourversion-dot-yourappid.appspot.com```. When you login you'll land back on the default version so edit the URL manually to go back to the new version. Then click around. Make sure everything is working!

1. Go to the [Google Cloud Console](http://cloud.google.com/console) for your App Engine app. To to the App Engine section. Go to the versions section. Select your newly deployed version. Click "make default". Confirm that when you load ```yourappid.appspot.com``` (without the explicit version prefix) that you see the new version of the code running.

1. Congratulations, you are done!
