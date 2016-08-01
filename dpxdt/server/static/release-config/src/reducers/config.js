/* @flow */

const SAVE = 'CONFIG::SAVE'

type ReleaseConfigType = {
  paths: Array<{
    path: string,
    injectCss:
    string,
    injectJs: string,
  }>,
  hostname: string,
  staging_hostname: string,
  injectCss: string,
  injectJs: string,
  userAgent: string,
  cookies: Array<string>,
  resourcesToIgnore: Array<string>,
  resourceTimeoutMs: number,
  httpUserName: string,
  httpPassWord: string,
  webdriverRemote: {
    command_executor: string,
    desired_capabilities: Array<string>,
  },
};

type ConfigState = {
  [key: string]: ReleaseConfigType,
};

export const BLANK_SETTINGS = {
  paths: [
    {
      injectCss: '',
      injectJs: '',
      name: 'About',
      path: 'about',
    },

  ],

  run_host: 'https://www.shift.com',
  ref_host: 'https://shiftcars1.appspot.com',
  injectCss: '',
  injectJs: '',
  userAgent: '',
  cookies: [''],
  resourcesToIgnore: [
    'segment.com',
    'fb.com',
  ],
  resourceTimeoutMs: 60,
  httpUserName: '',
  httpPassWord: '',

  command_executor: 'http://lindseysimon2:H1Nnszrxzxpv75fifTNn@hub.browserstack.com:80/wd/hub',
  desired_capabilities: [
    "{'browser': 'Firefox', 'browser_version': '46.0', 'os': 'OS X', 'os_version': 'El Capitan', 'resolution': '1024x768'}",
    //"{'platform': 'MAC', 'browserName': 'iPhone', 'device': 'iPhone 5' }",
  ]
};

const INITIAL_STATE: ConfigState = {
  builds: {},
};

const dataToReleaseConfig = (data) => {
  let releaseConfig = [];
  data.desired_capabilities.forEach(capability => {
    data.paths.forEach(pathObj => {
      let runConfig =  {
        resourcesToIgnore: data.resourcesToIgnore,
        resourceTimeoutMs: data.resourceTimeoutMs,
        command_executor: data.command_executor,
        desired_capabilities: capability,
        userAgent: data.userAgent,
      };
      runConfig.injectJs = ((data.injectJS || '') + (pathObj.injectJs || '')) || null;
      runConfig.injectCss = ((data.injectCss || '') + (pathObj.injectCss || '')) || null;

      let testConfig = {
        name: pathObj.name,
        run_url: data.run_host + '/' + pathObj.path,
        run_config: runConfig,
      };

      if (data.ref_host) {
        testConfig = Object.assign({
          ref_url: data.ref_host + '/' + pathObj.path,
          ref_config: runConfig,
        }, testConfig);
      }
      releaseConfig.push(testConfig);
    });
  });
  return releaseConfig;
};


const reducer = (state: ConfigState = INITIAL_STATE, action) => {
  switch (action.type) {
    case SAVE:
      console.log('SAVE', action.build_id, action.data, state)
      let builds = { ...state.builds, [action.build_id]: action.data };
      return { ...state, builds: builds };
    default:
      return state;
  }
};

/**
 * Simulates data loaded into this reducer from somewhere
 */
//const TEST_SERVER_VALIDATION = false;
export function save(build_id: number, data: ReleaseConfigType, action='saveAndRun') {
  return dispatch => {
    let releaseConfig = dataToReleaseConfig(data);
    let requestData = JSON.stringify({
      action,
      build_id,
      csrf_token: window.CSRF_TOKEN,
      release_config: releaseConfig,
    });
    return new Promise((resolve, reject) => {
      $.ajax({
        contentType: 'application/json; charset=utf-8',
        data: requestData,
        dataType: 'json',
        success: data => {
          resolve(data);
        },
        error: err => {
          reject(err);
        },
        processData: false,
        type: 'POST',
        url: '/settings/release/config'
      });
      /*
      window.setTimeout(() => {
        if (TEST_SERVER_VALIDATION) {
          console.log('failed on the server');
          reject({ ref_host: 'This field is messed up' });
        } else {
          resolve();
        }
      }, 200); // simulate server latency
      */
    }).then(
      resp => {
        console.log('save success!', resp)
        window.CSRF_TOKEN = resp.csrf_token;
        dispatch({
          type: SAVE,
          data: data,
          build_id: build_id,
        });
      },
      err => {
        console.log('err', err)
        return err;
      });
  };
}


export default reducer;