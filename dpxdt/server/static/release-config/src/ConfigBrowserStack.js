/* @flow */
import React, { Component } from 'react';
import {
  ControlLabel,
} from 'react-bootstrap';

import FormGroupControl from './FormGroupControl.js';

type ConfigBrowserStackProps = {
  buildID: string,
  fields: Object,
};

const ConfigBrowserStack = (props: ConfigBrowserStackProps) => {
  const {
    fields: {
      command_executor,
      desired_capabilities,
    },
  } = props;
  return (
    <div>
      <p>
        <a href="https://www.browserstack.com/automate/python" target="_blank">
          Use Browserstack to get your configuration
        </a>
      </p>

      <FormGroupControl
        field={command_executor}
        label="Command Executor"
        placeholder="http://username:password@hub.browserstack.com:80/wd/hub"
      />

      <ControlLabel>Desired Capabilities</ControlLabel>
      {desired_capabilities.map((desired_capability, i) =>
        <FormGroupControl
          arrayFields={desired_capabilities}
          arrayIndex={i}
          field={desired_capability}
          key={i}
        />)}

    </div>
  );
};

export default ConfigBrowserStack;