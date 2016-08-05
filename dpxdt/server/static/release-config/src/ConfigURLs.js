/* @flow */
import React from 'react';
import {
  FormControl,
  InputGroup,
  Table,
} from 'react-bootstrap';

import { AddRemoveButtons } from './FormGroupControl.js';


type PathObj = Object; // <- redux form field
type PathConfigProps = {
  i: number,
  paths?: Array<PathObj>,
  pathObj: PathObj,
};

const PathConfig = ({ i, pathObj, paths  }: PathConfigProps) => (
  <tr>
    <td style={{textAlign:'center',verticalAlign:'middle'}}>{i + 1}</td>
    <td>
      <FormControl
        placeholder="About Page"
        style={{ minWidth:'150px', width:'1%' }}
        {...pathObj.name}
      />
    </td>
    <td>
      <InputGroup>
        <InputGroup.Addon>/</InputGroup.Addon>
        <FormControl
          placeholder="about"
          {...pathObj.path}
        />
      </InputGroup>
    </td>
    <td style={{ width:'1%' }}>
      <AddRemoveButtons arrayFields={paths} arrayIndex={i} />
    </td>
  </tr>
);


type ConfigURLsProps = {
  buildID: string,
  fields: Object,
};

const ConfigURLs = (props: ConfigURLsProps) => {
  const {
    fields: {
      paths,
    },
  } = props;
  return (
    <div>
      <Table striped bordered hover responsive>
        <thead>
          <tr>
            <th></th>
            <th>Name</th>
            <th>Path</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {paths.map((pathObj, i) =>
            <PathConfig i={i} key={i} pathObj={pathObj} paths={paths} />)}
        </tbody>
      </Table>
    </div>
  );
};

export default ConfigURLs;
