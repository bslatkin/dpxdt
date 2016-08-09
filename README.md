# Depicted—dpxdt

Make continuous deployment safe by comparing before and after webpage screenshots for each release. Depicted shows when any visual, perceptual differences are found. This is the ultimate, automated end-to-end test.

**[View the test instance here](https://dpxdt-test.appspot.com)**

Depicted is:

- A [local command-line tool](#local-depicted) for doing perceptual diff testing.
- An [API server and workflow](#depicted-server) for capturing webpage screenshots and automatically generating visual, perceptual difference images.
    - A workflow for teams to coordinate new releases using pdiffs.
    - A client library for integrating the server with existing continuous integration.
    - Built for portability; server runs with SQLite, MySQL, behind the firewall, etc.
- A wrapper of [PhantomJS](http://phantomjs.org/) for screenshots.
- Open source, Apache 2.0 licensed.
- Not a framework, not a religion.

**Depicted is not finished! [Please let us know if you have feedback or find bugs](https://github.com/bslatkin/dpxdt/issues/new).**

See [this video for a presentation](http://youtu.be/UMnZiTL0tUc) about how perceptual diffs have made continuous deployment safe.

[![Build Status](https://travis-ci.org/bslatkin/dpxdt.svg?branch=master)](https://travis-ci.org/bslatkin/dpxdt)

# Local Depicted

Local `dpxdt` is a tool for generating screenshots. It reads in a YAML config file and generates screenshots using PhantomJS. This makes sense for testing reusable tools (e.g. libraries) which aren't "deployed" in the way that a traditional web app is.

To get started with run:

    pip install dpxdt

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

## Configuration

The screenshot is 400x300 with a transparent background. This is probably not what you want! You can override these settings with the `config` stanza:

```yaml
# (tests/test.yaml)
setup: |
    python -m SimpleHTTPServer

waitFor:
    url: http://localhost:8000/demo.html
    timeout_secs: 5

tests:
  - name: demo
    url: http://localhost:8000/demo.html
    config:
        viewportSize:
            width: 800
            height: 600
        injectCss: |
            body {
              background-color: white;
            }
```

You can find a complete list of config settings in [capture.js](https://github.com/bslatkin/dpxdt/blob/master/dpxdt/client/capture.js), but the most common ones are `viewportSize`, `injectCss` and `injectJs`.

## Perceptual Diffs

Local dpxdt has two modes: `update` and `test`. As we've seen above, `update` saves screenshots to the test directory. `test` takes screenshots and compares them to the saved versions.

For example:

    $ dpxdt test tests
    Request for http://localhost:8000/demo.html succeeded, continuing with tests...
    demo: Running webpage capture process
    demo: Resizing reference image
    demo: Running perceptual diff process
    demo passed (no diff)
    All tests passed!

Now if we change `demo.html`:

```html
<!-- demo.html -->
<h2>dpxdt local demo</h2>
<p>dpxdt may be used to spot changes on local web servers.</p>
```

and run the test command again:

    $ dpxdt test tests
    Request for http://localhost:8000/demo.html succeeded, continuing with tests...
    demo: Running webpage capture process
    demo: Resizing reference image
    demo: Running perceptual diff process
    demo failed
      0.0385669 distortion
      Ref:  /tmp/.../tmp6rMuVH/ref_resized
      Run:  /tmp/.../tmp6rMuVH/screenshot.png
      Diff: /tmp/.../tmp6rMuVH/diff.png
     (all):     /tmp/.../tmp6rMuVH/{ref_resized,screenshot.png,diff.png}
    1 test(s) failed.

dpxdt has output a triplet of images: reference, run and diff. You can open all of them at once by copying the (all) line. For example, on Mac OS X:

    open /tmp/.../tmp6rMuVH/{ref_resized,screenshot.png,diff.png}

Here's what they look like:

| Which  | Image |
| ---:  | ----- |
| Reference  | ![reference image](http://cl.ly/image/33073K33231z/ref_resized.png) |
| Run  | ![run image](http://cl.ly/image/0e1X3e0Q3v0J/screenshot.png)        |
| Diff | ![diff image](http://cl.ly/image/423Y3q0g3c23/diff.png)             |

The red portions of the diff image highlight where the change is. These might be difficult to spot without a perceptual diff!

## Shared Configurations

Most tests will share a similar `config` stanza. As your you write more tests, this gets quite repetitive. YAML supports a syntax for references which greatly reduces the repetition:

```yaml
# (tests/test.yaml)
setup: |
    python -m SimpleHTTPServer

waitFor:
    url: http://localhost:8000/demo.html
    timeout_secs: 5

standard-config: &stdconfig
    viewportSize:
        width: 800
        height: 600
    injectCss: >
        body {
          background-color: white;
        }

tests:
  - name: demo
    url: http://localhost:8000/demo.html
    config: *stdconfig

  - name: demo-with-click
    url: http://localhost:8000/demo.html
    config:
        <<: *stdconfig
        injectJs: |
            $('button').click();
```

As the last example shows, you can "mix in" a config and add to it. If you include a stanza which is already in the mixed-in config (e.g. `viewportSize`), it will override it.

# Depicted Server

Depicted is written in portable Python. It uses Flask and SQLAlchemy to make it easy to run in your environment. It works with SQLite out of the box right on your laptop. The API server can also run on VMs. The workers run [ImageMagick](http://www.imagemagick.org/Usage/compare/) and [PhantomJS](http://phantomjs.org/) as subprocesses. I like to run the worker on a cloud VM, but you could run it on your behind a firewall if that's important to you.

Topics in this section:

- [Running the server locally](#running-the-server-locally)
- [How to use Depicted effectively](#how-to-use-depicted-effectively)
- [Example tools](#example-tools)
- [The API documentation](#api)
- [Deployment to production (Sqlite, etc)](#deployment)

## Running the server locally

**WARNING LABEL**: This is *only* for local development. If you actually want a reliable server that will run for days, see [the section on deployment](#deployment) below.

1. Have a version of [Python 2.7](http://www.python.org/download/releases/2.7/) installed.
1. Download [PhantomJS](http://phantomjs.org/) for your machine.
1. Download [ImageMagick](http://www.imagemagick.org/script/binary-releases.php) for your machine.
1. Clone this git repo in your terminal:

        git clone https://github.com/bslatkin/dpxdt.git

1. ```cd``` to the repo directory:
1. Create a new python virtual environment and activate it:

        virtualenv .
        source bin/activate

1. Install all dependencies into the environment:

        pip install -r requirements.txt
        pip install -e .

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
1. Deactivate your virtual environment

        deactivate

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

If your web site has got HTTP Basic authentication, then you can add the username and password with additionals parameters
http_username and http_password. Previous example would be:

```
./dpxdt/tools/site_diff.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    --crawl_depth=1 \
    --http_username=user \
    --http_password=pass \
    http://www.example.com/my/website/here
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

Same as site_diff.py, if your web sites have got HTTP Basic authentication, then you can add the username and password with additionals parameters
http_username and http_password. Note that the password must be the same for both web sites (or one of them must have no authentication enabled for example).

Previous example would be:

```
./dpxdt/tools/url_pair_diff.py \
    --upload_build_id=1234 \
    --release_server_prefix=https://my-dpxdt-apiserver.example.com/api \
    --release_client_id=<your api key> \
    --release_client_secret=<your api secret> \
    --http_username=user \
    --http_password=pass \
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
            "injectJs": "document.getElementById('foobar').innerText = 'bar';"
        },
        "ref_url": "http://localhost:5000/static/dummy/dummy_page1.html",
        "ref_config": {
            "viewportSize": {
                "width": 1024,
                "height": 768
            },
            "injectCss": "#foobar { background-color: goldenrod; }",
            "injectJs": "document.getElementById('foobar').innerText = 'foo';"
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

- *build_id*: ID of the build.
- *release_name*: Name of the new release.
- *url*: URL of the homepage of the new release. Only present for humans who need to understand what a release is for.

##### Returns

- *build_id*: ID of the build.
- *release_name*: Name of the release that was just created.
- *release_number*: Number assigned to the new release by the system.
- *url*: URL of the release's homepage.

#### /api/find_run

Finds the last good run of the given name for a release. Returns an error if no run previous good release exists.

##### Parameters

- *build_id*: ID of the build.
- *run_name*: Name of the run to find the last known-good version of.

##### Returns

- *build_id*: ID of the build.
- *release_name*: Name of the last known-good release for the run.
- *release_number*: Number of the last known-good release for the run.
- *run_name*: Name of the run that was found. May be null if a run could not be found.
- *url*: URL of the last known-good release for the run. May be null if a run could not be found.
- *image*: Artifact ID (SHA1 hash) of the screenshot image associated with the run. May be null if a run could not be found.
- *log*: Artifact ID (SHA1 hash) of the log file from the screenshot process associated with the run. May be null if a run could not be found.
- *config*: Artifact ID (SHA1 hash) of the config file used for the screenshot process associated with the run. May be null if a run could not be found.

#### /api/request_run

Requests a new run for a release candidate. Causes the API system to take screenshots and do pdiffs. When `ref_url` and `ref_config` are supplied, the system will run two sets of captures (one for the baseline, one for the new release) and then compare them. When `rel_url` and `ref_config` are not specified, the last good run for this build is found and used for comparison.

##### Parameters

- *build_id*: ID of the build.
- *release_name*: Name of the release.
- *release_number*: Number of the release.
- *url*: URL to request as a run.
- *config*: JSON data that is the config for the new run.
- *ref_url*: URL of the baseline to request as a run.
- *ref_config*: JSON data that is the config for the baseline of the new run.

###### Format of `config`

The config passed to the `request_run` function may have any or all of these fields. All fields are optional and have reasonably sane defaults.

```json
{
    "clipRect": {
        "left": 0,
        "top": 0,
        "width": 100,
        "height": 200
    },
    "cookies": [
        {
            "name": "my-cookie-name",
            "value": "my-cookie-value",
            "domain": ".example.com"
        }
    ],
    "httpUserName": "my-username",
    "httpPassword": "my-password",
    "injectCss": ".my-css-rules-here { display: none; }",
    "injectJs": "document.getElementById('foobar').innerText = 'foo';",
    "injectHeaders": {
        "domain.com": { "X-CustomHeader": "HeaderValue" }
    },
    "resourcesToIgnore": ["www.google-analytics.com", "bad.example.com"],
    "resourceTimeoutMs": 60000,
    "userAgent": "My fancy user agent",
    "viewportSize": {
        "width": 1024,
        "height": 768
    }
}
```

##### Returns

- *build_id*: ID of the build.
- *release_name*: Name of the release.
- *release_number*: Number of the release.
- *run_name*: Name of the run that was created.
- *url*: URL that was requested for the run.
- *config*: Artifact ID (SHA1 hash) of the config file that will be used for the screenshot process associated with the run.
- *ref_url*: URL that was requested for the baseline reference for the run.
- *ref_config*: Artifact ID (SHA1 hash) of the config file used for the baseline screenshot process of the run.

#### /api/upload

Uploads an artifact referenced by a run.

##### Parameters

- *build_id*: ID of the build.
- *(a single file in the multipart/form-data)*: Data of the file being uploaded. Should have a filename in the mime headers so the system can infer the content type of the uploaded asset.

##### Returns

- *build_id*: ID of the build.
- *sha1sum*: Artifact ID (SHA1 hash) of the file that was uploaded.
- *content_type*: Content type of the artifact that was uploaded.

#### /api/report_run

Reports data for a run for a release candidate. May be called multiple times as progress is made for a run. Should not be called once the screenshot image for the run has been assigned.

##### Parameters

- *build_id*: ID of the build.
- *release_name*: Name of the release.
- *release_number*: Number of the release.
- *run_name*: Name of the run.
- *url*: URL associated with the run.
- *image*: Artifact ID (SHA1 hash) of the screenshot image associated with the run.
- *log*: Artifact ID (SHA1 hash) of the log file from the screenshot process associated with the run.
- *config*: Artifact ID (SHA1 hash) of the config file used for the screenshot process associated with the run.
- *ref_url*: URL associated with the run's baseline release.
- *ref_image*: Artifact ID (SHA1 hash) of the screenshot image associated with the run's baseline release.
- *ref_log*: Artifact ID (SHA1 hash) of the log file from the screenshot process associated with the run's baseline release.
- *ref_config*: Artifact ID (SHA1 hash) of the config file used for the screenshot process associated with the run's baseline release.
- *diff_image*: Artifact ID (SHA1 hash) of the perceptual diff image associated with the run.
- *diff_log*: Artifact ID (SHA1 hash) of the log file from the perceptual diff process associated with the run.
- *diff_failed*: Present and non-empty string when the diff process failed for some reason. May be missing when diff ran and reported a log but may need to retry for this run.
- *run_failed*: Present and non-empty string when the run failed for some reason. May be missing when capture ran and reported a log but may need to retry for this run.
- *distortion*: Float amount of difference found in the diff that was uploaded, as a float between 0 and 1

##### Returns
Nothing but success on success.

#### /api/runs_done

Marks a release candidate as having all runs reported.

##### Parameters

- *build_id*: ID of the build.
- *release_name*: Name of the release.
- *release_number*: Number of the release.

##### Returns

- *results_url*: URL where a release candidates run status can be viewed in a web browser by a build admin.

## Deployment

### Sqlite instance

Here's how to run a production-grade version of the server on your a machine using sqlite as the database. This will also work on VMs if you put the deployment directory on a persistent filesystem.

1. `cd` into the `deployment` directory:
1. Run this command:

        make sqlite_deploy

1. `cd` into the `sqlite_deploy` directory
1. Create a new project on [cloud console](https://console.developers.google.com/project)
    1. In the _APIs & auth / Credentials_ section, create a new OAuth Client ID
        1. Select "Web application"
        1. Fill in the _Consent screen_ information as appropriate
        1. Set _Authorized redirect URIs_ to `https://your-project.example.com/oauth2callback`
    1. Copy the _Redirect URI_, _Client ID_, and _Client secret_ values into corresponding fields in `settings.cfg`
    1. Update the `SESSION_COOKIE_DOMAIN` value in `settings.cfg` to match the _Redirect URI_.
1. Copy the `sqlite_deploy` directory to wherever you want to run the server
1. In the `sqlite_deploy` directory on the server, create a new python virtual environment:

        virtualenv .

1. Run the server

        ./run.sh

1. Note:
    - All of the data for the server will live in the `sqlite_deploy` directory in a file named `data.db`.
    - You'll need to install [PhantomJS](http://phantomjs.org/build.html)
    - You'll need to install [ImageMagick](https://packages.debian.org/jessie/imagemagick)
    - You may need to install [virtualenv](https://packages.debian.org/jessie/python/python-virtualenv) on your system to get the server to work.
    - You may want to install a package like [tmpreaper](https://packages.debian.org/jessie/tmpreaper) to ensure you don't fill up `/tmp` with test images and log files.
    - You may want to run the server under a supervisor like [runit](https://packages.debian.org/jessie/runit) so it's always up.

### Upgrading production and migrating your database

TODO: Update this for deployment

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
