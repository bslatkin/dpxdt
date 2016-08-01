/* @flow */
import React, { Component } from 'react';
import {
  Button,
  ControlLabel,
  FormControl,
  FormGroup,
  InputGroup,
} from 'react-bootstrap';

type FormGroupControlProps = {
  arrayFields?: Array<Object>,
  arrayIndex?: number,
  field: Object,
  getValidationState?: Function,
  label: string,
  placeholder?: string,
};

const ValidationState = {
  ERROR: 'error',
  SUCCESS: 'success',
};

export default class FormGroupControl extends Component {
  props: FormGroupControlProps;

  getValidationState(field) {
    if (field.error) {
      return ValidationState.ERROR;
    } else if (field.value && !field.error) {
      return ValidationState.SUCCESS;
    }
  }

  render() {
    let { arrayIndex, arrayFields, field, label, placeholder, getValidationState, ...props } = this.props;
    getValidationState = getValidationState || this.getValidationState;
    let validationState = getValidationState(field);
    return (
      <FormGroup
        {...props}
        controlId={field.name + arrayIndex}
        validationState={validationState}
        >
        {label && <ControlLabel>{label}</ControlLabel>}
        {
          arrayFields ?
          <ArrayInputWithAddRemoveButtons
            arrayFields={arrayFields}
            arrayIndex={arrayIndex}
            field={field}
            validationState={validationState}
          /> :
          <FormControl
            placeholder={placeholder}
            {...field}
          />
        }
        {
          //arrayFields ?
          //null :
          //<FormControl.Feedback />
        }
        {
          field.error && <p className="help-block" style={{marginBottom: 0}}>{field.error}</p>
        }
      </FormGroup>
    );
  }
}

export const AddRemoveButtons = ({ arrayFields, arrayIndex }) => (
  <InputGroup.Button>
    {
      arrayIndex === arrayFields.length - 1 && arrayFields.length > 1 ?
      <Button type="button" onClick={() => {
        arrayFields.removeField(arrayIndex);
      }}>-</Button> :
      null
    }
    {
      arrayIndex === arrayFields.length - 1 ?
      <Button type="button" onClick={() => {
        // `{}` ensures an empty child for objects is added, works fine for flat fields.
        arrayFields.addField({});
      }}>+</Button> :
      <Button type="button" onClick={() => {
        arrayFields.removeField(arrayIndex);
      }}>-</Button>
    }
  </InputGroup.Button>
);

const ArrayInputWithAddRemoveButtons = ({ arrayFields, arrayIndex, field, validationState }) => (
  <InputGroup>
    <FormControl {...field} />
    <AddRemoveButtons arrayFields={arrayFields} arrayIndex={arrayIndex} />
  </InputGroup>
);
