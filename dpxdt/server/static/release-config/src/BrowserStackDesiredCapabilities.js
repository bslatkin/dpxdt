/* @flow */
import React from 'react';
import {
  ControlLabel,
} from 'react-bootstrap';

import BrowserStackData from './BrowserStackData.js';

export default class BrowserStackDesiredCapabilities extends React.Component {
  render() {
    return (
      <div class="doc-options-lists doc-desktop-lists">
        <ul>
          <li><a href="#" data-os="win10" class="icon-browser-sprite icon-windows8">Windows 10</a></li>
          <li><a href="#" data-os="win8.1" class="icon-browser-sprite icon-windows8">Windows 8.1</a></li>
          <li><a href="#" data-os="win8" class="icon-browser-sprite icon-windows8">Windows 8</a></li>
          <li><a href="#" data-os="win7" class="active icon-browser-sprite icon-windows7">Windows 7</a></li>
          <li><a href="#" data-os="winxp" class="icon-browser-sprite icon-windowsxp">Windows XP</a></li>
        </ul>
        <ul>
          <!-- <li><a href="#" data-os="macsie" class="icon-browser-sprite icon-macsie">OS X Sierra</a></li> -->
          <li><a href="#" data-os="macelc" class="icon-browser-sprite icon-macelc">OS X El Capitan</a></li>
          <li><a href="#" data-os="macyos" class="icon-browser-sprite icon-osxyosemite">OS X Yosemite</a></li>
          <li><a href="#" data-os="macmav" class="icon-browser-sprite icon-osxmavericks">OS X Mavericks</a></li>
          <li><a href="#" data-os="macml" class="icon-browser-sprite icon-osxmountainlion">OS X Mountain Lion</a></li>
          <li><a href="#" data-os="maclion" class="icon-browser-sprite icon-osxlion">OS X Lion</a></li>
          <li><a href="#" data-os="macsl" class="icon-browser-sprite icon-osxsnowleopard">OS X Snow Leopard</a></li>
        </ul>
      </div>
      <div class="doc-os-mobile">
        <div class="doc-options-title">Mobile &amp; Tablet Emulators</div>
        <ul>
          <li><a href="#" data-os="ios" data-type="mobile" class="icon-browser-sprite icon-ios"><span class="os-name">iOS</span><span class="os-desc">Mobile Safari</span></a></li>
          <li ><a href="#"data-os="android" data-type="mobile" class="icon-browser-sprite icon-android"><span class="os-name">Android</span><span class="os-desc">Android Browser</span></a></li>
        </ul>
      </div>
    );
  }
}
