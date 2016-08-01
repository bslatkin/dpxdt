import React, { Component } from 'react';
import { Router, Route, browserHistory } from 'react-router'
import { applyMiddleware, compose, createStore, combineReducers } from 'redux';
import persistState from 'redux-localstorage';
import { reducer as formReducer } from 'redux-form';
import { Provider } from 'react-redux';
import thunk from 'redux-thunk';
import { syncHistoryWithStore, routerReducer } from 'react-router-redux';

import configReducer from './reducers/config.js';

const enhancer = compose(
  applyMiddleware(thunk),
  persistState('release_config'),
);

const store = createStore(combineReducers({
  release_config: configReducer,
  form: formReducer,
  routing: routerReducer,
}), enhancer);

// Create an enhanced history that syncs navigation events with the store
const history = syncHistoryWithStore(browserHistory, store)

import './App.css';

import ConfigForm from './ConfigForm.js';

export default class App extends Component {
  render() {
    return (
      <Provider store={store}>
        <Router history={history}>
          <Route path="/settings/release/config" component={ConfigForm}>
          </Route>
        </Router>
      </Provider>
    );
  }
}
