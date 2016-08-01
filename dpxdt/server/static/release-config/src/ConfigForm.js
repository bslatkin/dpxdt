/* @flow */
import React, { Component } from 'react';
import { reduxForm } from 'redux-form';
import {
  Button,
  Col,
  Form,
  FormGroup,
  Panel,
} from 'react-bootstrap';

import { BLANK_SETTINGS, save } from './reducers/config.js';

import ConfigBrowserStack from './ConfigBrowserStack.js';
import ConfigSettings from './ConfigSettings.js';
import ConfigURLs from './ConfigURLs.js';


export const fields = [
  'command_executor',
  'desired_capabilities[]',
  'paths[].name',
  'paths[].path',
  'resourcesToIgnore[]',
  'resourceTimeoutMs',
  'run_host',
  'ref_host',
];


class ConfigForm extends Component {
  /*
  componentWillReceiveProps(nextProps) {
    if (nextProps.dirty && nextProps.valid &&
        nextProps.values !== this.props.values) {
     this.props.save(nextProps.values)
    }
  }
  */

  handleSubmit = (data, dispatch) => {
    console.log('handleSubmit data', data);

    return new Promise((resolve, reject) => {
      return this.props.save(this.props.location.query.build_id, data).then(err => {
        console.log('got err resp?', !!err)
        if (err) {
          reject(err);
        } else {
          resolve()
        }
      });
    });
  };

  render() {
    const buildID = this.props.location.query.build_id;
    return (
      <div className="container-fluid">
        <Form onSubmit={this.props.handleSubmit(this.handleSubmit)}>
          <Panel header={<h3>General Settings</h3>}>
            <ConfigSettings buildID={buildID} fields={this.props.fields} />
          </Panel>
          <Panel header={<h3>Capture Configuration</h3>}>
            <ConfigBrowserStack buildID={buildID} fields={this.props.fields} />
          </Panel>
          <Panel header={<h3>Screenshot Paths</h3>}>
            <ConfigURLs buildID={buildID} fields={this.props.fields} />
          </Panel>

          <FormGroup>
            <Col sm={12}>
              <Button type="submit" bsSize="large" bsStyle="primary" onClick={save}>
                Save
              </Button>
            </Col>
          </FormGroup>
        </Form>
      </div>
    );
  }
}

ConfigForm = reduxForm({ // <----- THIS IS THE IMPORTANT PART!
  form: 'form-release-config',
  fields,
},
(state, ownProps) => ({ // mapStateToProps
  initialValues: state.release_config.builds[ownProps.location.query.build_id] || Object.assign({}, BLANK_SETTINGS),
}),
{
  save: save
})(ConfigForm);

export default ConfigForm;