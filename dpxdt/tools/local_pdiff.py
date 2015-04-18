#!/usr/bin/env python
'''Run a perceptual diff test locally.

To run:
    source ./common.sh
    ./dpxdt/tools/local_pdiff.py test dpxdt/tools/local_pdiff_demo

This will run the tests described in dpxdt/tools/local_pdiff_demo/*.yaml.
See those files for details.
'''

import copy
import fnmatch
import glob
import json
import logging
import os
import requests
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback

# Local Libraries
import gflags
FLAGS = gflags.FLAGS
import pyimgur
import yaml

# Local modules
from dpxdt.client import capture_worker
from dpxdt.client import fetch_worker
from dpxdt.client import pdiff_worker
from dpxdt.client import process_worker
from dpxdt.client import timer_worker
from dpxdt.client import utils
from dpxdt.client import workers

FLAGS.SetDefault('phantomjs_binary', 'phantomjs')
FLAGS.SetDefault('phantomjs_timeout', 20)

gflags.DEFINE_boolean(
        'list_tests', False,
        'Set this to list the names of all tests instead of running them.')

gflags.DEFINE_string(
        'test_filter', '',
        'Run a subset of tests. Pass a test name to run just that test, or '
        'use a * to match a set of tests. See '
        'https://code.google.com/p/googletest/wiki/AdvancedGuide'
        '#Running_a_Subset_of_the_Tests for full syntax.')

gflags.DEFINE_string(
        'imgur_client_id', '',
        'When this is set, dpxdt will upload all screenshots from failing '
        'tests to Imgur using their API. This is helpful when running tests '
        'on a Travis-CI worker, for instance. You must register an app with '
        'Imgur to use this.')

MODES = ['test', 'update']

# global tracker
FAILED_TESTS = 0



def should_run_test(name, pattern):
    '''Given a test_filter pattern and a test name, should the test be run?'''
    if pattern == '': return True

    def matches_any(name, parts):
        for part in parts:
            if fnmatch.fnmatch(name, part):
                return True
        return False

    positive_negative = pattern.split('-')
    positive = positive_negative[0]
    if positive:
        # There's something here -- have to match it!
        parts = positive.split(':')
        if not matches_any(name, parts): return False

    if len(positive_negative) > 1:
        negative = positive_negative[1]
        parts = negative.split(':')
        if matches_any(name, parts): return False

    return True


class OneTestWorkflowItem(workers.WorkflowItem):
    '''Runs an individual capture & pdiff (or update) based on a config.'''

    def run(self, test_config, ref_dir, tmp_dir, mode, heartbeat=None, num_attempts=0):
        '''Build a CaptureAndDiffWorkflowItem for a test.

        Args:
            test_config: See test.yaml for structure of test_config.
        Returns: A CaptureAndDiffWorkflowItem
        '''
        assert 'name' in test_config
        name = test_config['name']

        if 'ref' in test_config:
            # This test has different ref/run arms.
            assert 'run' in test_config
            arm_config = { 'name': name }
            if mode == 'test':
                arm_config.update(test_config['run'])
            elif mode == 'update':
                arm_config.update(test_config['ref'])
            test_config = arm_config

        assert 'url' in test_config

        test_dir = tempfile.mkdtemp(dir=tmp_dir)
        log_file = os.path.join(test_dir, 'log.txt')
        output_path = os.path.join(test_dir, 'screenshot.png')

        logging.info('Test config:\n%s', json.dumps(test_config, indent=2))

        capture_config = copy.deepcopy(test_config.get('config', {}))
        capture_config['targetUrl'] = test_config['url']
        config_file = os.path.join(test_dir, 'config.json')
        json.dump(capture_config, open(config_file, 'w'), indent=2)

        ref_path = os.path.join(ref_dir, '%s.png' % name)
        if mode == 'test':
            assert os.path.exists(ref_path), (
                'Reference image %s does not exist. '
                'Try running in update mode.' % ref_path)
        elif mode == 'update':
            output_path = ref_path
            ref_path = None
        else:
            raise ValueError('Invalid mode %s' % mode)

        class NamedHeartbeat(workers.WorkflowItem):
            def run(self, message):
                yield heartbeat('%s: %s' % (name, message))

        try:
            yield CaptureAndDiffWorkflowItem(
                    name, log_file, config_file, output_path, ref_path,
                    heartbeat=NamedHeartbeat)
        except capture_worker.CaptureFailedError, e:
            if num_attempts >= e.max_attempts:
                yield heartbeat('Unable to capture screenshot after %d tries.' % num_attempts)
                raise e
            else:
                num_attempts += 1
                yield heartbeat('Capture failed, retrying (%d)' % num_attempts)
                yield OneTestWorkflowItem(test_config, ref_dir, tmp_dir, mode,
                        heartbeat=heartbeat, num_attempts=num_attempts)


class CaptureAndDiffWorkflowItem(workers.WorkflowItem):

    def run(self, name, log_file, config_file, output_path, ref_path, heartbeat=None):
        yield heartbeat('Running webpage capture process')
        yield heartbeat('  Logging to %s' % log_file)

        capture_failed = True
        failure_reason = None

        try:
            returncode = yield capture_worker.CaptureWorkflow(log_file, config_file, output_path)
        except (process_worker.TimeoutError, OSError), e:
            failure_reason = str(e)
        else:
            capture_failed = returncode != 0
            failure_reason = 'returncode=%s' % returncode

        if capture_failed:
            raise capture_worker.CaptureFailedError(
                FLAGS.capture_task_max_attempts,
                failure_reason)

        if ref_path is None:
            yield heartbeat('Updated %s' % output_path)
            return  # update mode

        # TODO: consolidate this code w/ DoPdiffQueueWorkflow.run
        ref_resized_path = os.path.join(os.path.dirname(output_path), 'ref_resized')
        diff_path = os.path.join(os.path.dirname(output_path), 'diff.png')
        max_attempts = FLAGS.pdiff_task_max_attempts

        yield heartbeat('Resizing reference image')
        returncode = yield pdiff_worker.ResizeWorkflow(
            log_file, ref_path, output_path, ref_resized_path)
        if returncode != 0:
            raise pdiff_worker.PdiffFailedError(
                max_attempts,
                'Could not resize reference image to size of new image')

        yield heartbeat('Running perceptual diff process')
        returncode = yield pdiff_worker.PdiffWorkflow(
            log_file, ref_resized_path, output_path, diff_path)

        # ImageMagick returns 1 if the images are different and 0 if
        # they are the same, so the return code is a bad judge of
        # successfully running the diff command. Instead we need to check
        # the output text.
        diff_failed = True

        # Check for a successful run or a known failure.
        distortion = None
        if os.path.isfile(log_file):
            log_data = open(log_file).read()
            if 'all: 0 (0)' in log_data:
                diff_path = None
                diff_failed = False
            elif 'image widths or heights differ' in log_data:
                # Give up immediately
                max_attempts = 1
            else:
                # Try to find the image magic normalized root square
                # mean and grab the first one.
                r = pdiff_worker.DIFF_REGEX.findall(log_data)
                if len(r) > 0:
                    diff_failed = False
                    distortion = r[0]

        if diff_failed:
            raise pdiff_worker.PdiffFailedError(
                max_attempts,
                'Comparison failed. returncode=%r' % returncode)

        else:
            if distortion:
                print '%s failed' % name
                print '  %s distortion' % distortion
                print '  Ref:  %s' % self.maybe_imgur(ref_resized_path)
                print '  Run:  %s' % self.maybe_imgur(output_path)
                print '  Diff: %s' % self.maybe_imgur(diff_path)

                # convenience line for copy/pasting
                print ' (all): %s/{%s}' % (
                        os.path.dirname(output_path),
                        ','.join(map(os.path.basename,
                            [ref_resized_path, output_path, diff_path])))
                global FAILED_TESTS
                FAILED_TESTS += 1

            else:
                print '%s passed (no diff)' % name

        # TODO: delete temp files

    def maybe_imgur(self, path):
        '''Uploads a file to imgur if requested via command line flags.

        Returns either "path" or "path url" depending on the course of action.
        '''
        if not FLAGS.imgur_client_id:
            return path

        im = pyimgur.Imgur(FLAGS.imgur_client_id)
        uploaded_image = im.upload_image(path)
        return '%s %s' % (path, uploaded_image.link)


class SetupStep(object):
    '''Logic for running and finishing the setup step of a pdiff test.'''

    def __init__(self, config, tmp_dir):
        '''Config is the top-level test config YAML object.'''
        self._config = config
        self._setup = config.get('setup')
        self._tmp_dir = tmp_dir
        self._setup_proc = None

    def run(self):
        if not self._setup: return

        # Note: we cannot use ProcessWorkflow here because the setup script
        # is not expected to terminate (it typically spawns a long-lived server).
        setup_file = os.path.join(self._tmp_dir, 'setup.sh')
        log_file = os.path.join(self._tmp_dir, 'setup.log')
        logging.info('Executing setup step: %s', setup_file)
        open(setup_file, 'w').write(self._setup)

        # If the shell script launches its own subprocesses (e.g. servers),
        # then these will become orphans if we send SIGTERM to setup_proc. In
        # order to avoid this, we make the shell script its own process group.
        # See http://stackoverflow.com/a/4791612/388951
        with open(log_file, 'a') as output_file:
            self._setup_proc = subprocess.Popen(['bash', setup_file],
                stderr=subprocess.STDOUT,
                stdout=output_file,
                close_fds=True,
                preexec_fn=os.setsid)

        return {'script': setup_file, 'log': log_file}

    def terminate(self):
        if not self._setup_proc: return
        if self._setup_proc.pid > 0:
            # TODO: send SIGKILL after 5 seconds?
            os.killpg(self._setup_proc.pid, signal.SIGTERM)
            self._setup_proc.wait()


class WrappedProcessWorkflowItem(process_worker.ProcessWorkflow):
    '''A ProcessWorkflow which can be yielded inline.'''
    def __init__(self, log_path, args, timeout_seconds=30):
        process_worker.ProcessWorkflow.__init__(
            self, log_path, timeout_seconds=timeout_seconds)
        self._args = args

    def get_args(self):
        return self._args


class WaitForUrlWorkflowItem(workers.WorkflowItem):
    '''Waits for an URL to resolve, with a timeout.'''

    def run(self, tmp_dir, waitfor, heartbeat=None, start_time=None):
        assert 'url' in waitfor
        timeout = waitfor.get('timeout_secs', 10)
        if not start_time:
            start_time = time.time()

        class NotReadyError(Exception):
            pass

        try:
            url = waitfor['url']
            r = requests.head(url)
            if r.status_code != 200:
                yield heartbeat('Request for %s failed (%d)' % (url, r.status_code))
                raise NotReadyError()

            yield heartbeat('Request for %s succeeded, continuing with tests...' % url)
            return
        except requests.ConnectionError, NotReadyError:
            now = time.time()
            if now - start_time >= timeout:
                raise process_worker.TimeoutError()
            yield timer_worker.TimerItem(0.5)  # wait 500ms between checks
            yield WaitForUrlWorkflowItem(tmp_dir, waitfor, heartbeat, start_time)


class WaitForWorkflowItem(workers.WorkflowItem):
    '''This performs the "waitFor" step specified in a test config.'''
    def run(self, config, tmp_dir, heartbeat):
        waitfor = config.get('waitFor')
        if isinstance(waitfor, basestring):
            waitfor_file = os.path.join(tmp_dir, 'waitfor.sh')
            log_file = os.path.join(tmp_dir, 'waitfor.log')
            logging.info('Executing waitfor step: %s', waitfor_file)
            try:
                yield WrappedProcessWorkflowItem(log_file, ['bash', waitfor_file])
            except subprocess.CalledProcessError:
                yield heartbeat('waitFor returned error code\nSee %s' % log_file)
                raise

        elif 'url' in waitfor:
            yield WaitForUrlWorkflowItem(tmp_dir, waitfor, heartbeat)


class RunAllTestSuitesWorkflowItem(workers.WorkflowItem):
    '''Load test YAML files and add them to the work queue.'''

    def run(self, config_dir, mode):
        configs = glob.glob(os.path.join(config_dir, '*.yaml'))
        if not configs:
            raise ValueError('No yaml files found in %s' % config_dir)

        heartbeat=workers.PrintWorkflow

        for config_file in configs:
            config = yaml.load(open(config_file))
            assert 'tests' in config

            if FLAGS.list_tests:
                print '%s:' % config_file
                for test in config['tests']:
                    assert 'name' in test
                    print '  %s' % test['name']
            else:
                yield RunTestSuiteWorkflowItem(config_dir, config, mode, heartbeat)


class RunTestSuiteWorkflowItem(workers.WorkflowItem):
    '''Run a single YAML file's worth of tests.'''

    def run(self, config_dir, config, mode, heartbeat):
        tmp_dir = tempfile.mkdtemp()

        yield heartbeat('Running setup step')
        setup = SetupStep(config, tmp_dir)
        setup_files = setup.run()
        yield heartbeat('  logging to %s' % setup_files['log'])

        try:
            if config.get('waitFor'):
                try:
                    yield WaitForWorkflowItem(config, tmp_dir, heartbeat)
                except process_worker.TimeoutError:
                    # The raw exception has an excessively long stack trace.
                    # This at least adds some helpful context to the end.
                    sys.stderr.write('Timed out on waitFor step.\n')
                    return

            for test in config['tests']:
                assert 'name' in test
                name = test['name']
                if should_run_test(name, FLAGS.test_filter):
                    yield OneTestWorkflowItem(test, config_dir, tmp_dir, mode,
                        heartbeat=heartbeat)
                else:
                    logging.info('Skipping %s due to --test_filter=%s',
                            name, FLAGS.test_filter)
        finally:
            setup.terminate()  # kill server from the setup step.


class RepetitiveLogFilterer(object):
    '''Suppress repeated log entries from the same line in the same file.'''
    def __init__(self):
        self.last_source = None

    def filter(self, record):
        if FLAGS.verbose:
            return True
        source = '%s:%s' % (record.filename, record.lineno)
        if source == self.last_source:
            return False
        self.last_source = source

        return True


class CompactExceptionLogger(logging.Formatter):
    def formatException(self, ei):
        # Like logging.Formatter.formatException, but without the stack trace.
        if FLAGS.verbose:
            return super(CompactExceptionLogger, self).formatException(ei)
        else:
            return '\n'.join(traceback.format_exception_only(ei[0], ei[1]))


def usage(short=False):
    sys.stderr.write('Usage: %s [update|test] <testdir>\n' % sys.argv[0])
    if not short:
        sys.stderr.write('%s\n' % FLAGS)


def main(argv):
    try:
        argv = FLAGS(argv)
    except gflags.FlagsError, e:
        sys.stderr.write('%s\n' % e)
        usage()
        sys.exit(1)

    if len(argv) < 3:
        sys.stderr.write('Too few arguments\n')
        usage(short=True)
        sys.exit(1)

    mode = argv[1]
    assert mode in MODES, 'Invalid mode: %s (expected %r)' % (mode, MODES)

    config_dir = argv[2]
    assert os.path.isdir(config_dir), 'Expected directory, got %s' % config_dir

    utils.verify_binary('phantomjs_binary', ['--version'])
    utils.verify_binary('pdiff_compare_binary', ['--version'])
    utils.verify_binary('pdiff_composite_binary', ['--version'])

    assert os.path.exists(FLAGS.phantomjs_script)

    logging.basicConfig()
    logging.getLogger().addFilter(RepetitiveLogFilterer())
    logging.getLogger().handlers[0].setFormatter(CompactExceptionLogger())
    if FLAGS.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    coordinator = workers.get_coordinator()
    timer_worker.register(coordinator)

    global FAILED_TESTS
    FAILED_TESTS = 0
    item = RunAllTestSuitesWorkflowItem(config_dir, mode)
    item.root = True
    coordinator.input_queue.put(item, mode)

    coordinator.start()
    coordinator.wait_one()
    coordinator.stop()
    coordinator.join()

    if mode == 'test':
        if FAILED_TESTS > 0:
            sys.stderr.write('%d test(s) failed.\n' % FAILED_TESTS)
            sys.exit(1)
        else:
            sys.stderr.write('All tests passed!\n')
            sys.exit(0)


def run():
    # (intended to be run from package)

    FLAGS.phantomjs_script = os.path.join(
            os.path.dirname(__file__), '..', 'client', 'capture.js')

    main(sys.argv)


if __name__ == '__main__':
    run()
