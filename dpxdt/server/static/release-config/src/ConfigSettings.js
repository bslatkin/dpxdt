/* @flow */
import React, { Component } from 'react';
import { Button, Collapse, ControlLabel } from 'react-bootstrap';

import FormGroupControl from './FormGroupControl.js';

type ConfigSettingsProps = {
  buildID: string,
  fields: Object,
};

type ConfigSettingsState = {
  resourcesToIgnoreOpen: boolean,
};

export default class ConfigSettings extends Component {
  props: ConfigSettingsProps;
  state: ConfigSettingsState;

  constructor(props) {
    super(props);
    this.state = {
      resourcesToIgnoreOpen: false,
    };
  }

  render() {
    const {
      fields: {
        resourceTimeoutMs,
        resourcesToIgnore,
        run_host,
        ref_host,
      },
    } = this.props;
    return (
      <div>
        <FormGroupControl
          field={ref_host}
          label="Production"
          placeholder="http://www.google.com"
        />
        <FormGroupControl
          field={run_host}
          label="Staging"
          placeholder="http://canary.google.com"
        />
        <FormGroupControl
          field={resourceTimeoutMs}
          label="Resource Timeout (in ms)"
          placeholder="60000"
        />
        <h5
          onClick={ () => this.setState({ resourcesToIgnoreOpen: !this.state.resourcesToIgnoreOpen })}
        >
          <strong style={{ paddingRight: '1em' }}>
            Resources to Ignore
          </strong>
          <Button bsSize="xsmall">
            {this.state.resourcesToIgnoreOpen ? '-' : '+'}
          </Button>
        </h5>
        <Collapse in={this.state.resourcesToIgnoreOpen}>
          <div>
          {resourcesToIgnore.map((resourceToIgnore, i) =>
            <FormGroupControl
              arrayFields={resourcesToIgnore}
              arrayIndex={i}
              field={resourceToIgnore}
              key={i}
            />)
          }
          </div>
        </Collapse>
      </div>
    );
  }
}
