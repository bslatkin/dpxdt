dpdxt typically runs a server which generates screenshots, diffs them and deploys your new code to production. This model works well for published apps, but less well for library code which isn't "deployed" per se.

To facilitate this use case, dpxdt comes with a command line tool which can be used to generate a fixed set of screenshots and diffs without requiring a release server. Full example code  [here](https://github.com/bslatkin/dpxdt/tree/master/dpxdt/tools/local_pdiff_demo).

Quick Start
-----------

Install the command line tool:

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

Configuration
-------------

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

Perceptual Diffs
----------------

Local dpxdt has two modes: `update` and `test`. As we've seen above, `update` saves screenshots to the test directory. `test` takes screenshots and compares them to the saved versions.

For example:

    $ dpdxdt test tests
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

Shared Configurations
---------------------

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
