import React, { Component } from 'react';
import { Link } from 'react-router'
import {
  Grid,
  PageHeader,
} from 'react-bootstrap';

export default class Home extends Component {
  render() {
    let buildID = this.props.location.query.build_id;
    return (
      <div className="HomePage">
        <PageHeader style={{ textAlign:'center' }}>DPXDT</PageHeader>
        <Grid>
          <nav role="nav" className="breadcrumb">
            <Link
              activeClassName="active"
              className="breadcrumb-item"
              to={`/settings/release/config?build_id=${buildID}`}
              >Settings</Link>
            {' '}/{' '}
            <Link
              activeClassName="active"
              className="breadcrumb-item"
              to={`/settings/release/config/urls?build_id=${buildID}`}
              >URLs</Link>
          </nav>
          {this.props.children}
        </Grid>
      </div>
    )
  }
}