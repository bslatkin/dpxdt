/* Copyright 2013 Brett Slatkin
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

function fireClickEvent(el) {
    if (!el) {
        return;
    }
    var event = document.createEvent('MouseEvents');
    event.initMouseEvent('click', true, true, window, 0, 0, 0, 0, 0,
                         false, false, false, false, 0, null);
    el.dispatchEvent(event);
}


// See list of virtual keyboard codes here:
// https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent
function handleKeyPress(e) {
    var root = $('#root-container');
    if (!(root.hasClass('endpoint-view_run') ||
          root.hasClass('endpoint-view_image') ||
          root.hasClass('endpoint-view_log') ||
          root.hasClass('endpoint-view_config'))) {
        return;
    }

    switch (String.fromCharCode(e.which)) {
        case 'j':  // J - Next
        case 'J':
            fireClickEvent($('#next_button').get(0));
            break;

        case 'k':  // K - Previous
        case 'K':
            fireClickEvent($('#previous_button').get(0));
            break;

        case 'u':  // U - Up
        case 'U':
            var target = $('#test_link').get(0) || $('#release_link').get(0);
            fireClickEvent(target);
            break;

        case 'o':  // O - Open detailed view
        case 'O':
            fireClickEvent($('.run-image-link').get(0));
            break;

        case 'y':  // Y - Approve
        case 'Y':
            fireClickEvent($('#approve_button').get(0));
            break;

        case 'n':  // N - Reject
        case 'N':
            fireClickEvent($('#reject_button').get(0));
            break;

        case 'f':  // F - Flip
        case 'F':
            var flipLinks = $('.flip-link');
            var nextLink = null;
            for (var i = 0; i < flipLinks.length; i++) {
                var currentLink = flipLinks[i];
                if ($(currentLink).hasClass('flip-link-selected')) {
                    // Link to flip to is either the next one in the list after
                    // the currently selected, or the very first in the list.
                    nextLink = flipLinks[i + 1] || flipLinks[0];
                    break
                }
            }
            fireClickEvent(nextLink);
            break;

        case '1':  // 1 - Go to the before image
            var flipLinks = $('.flip-link');
            if (flipLinks.length == 3) {
                fireClickEvent(flipLinks[0]);
            }
            break;

        case '2':  // 2 - Go to the diff image
            var flipLinks = $('.flip-link');
            if (flipLinks.length == 3) {
                fireClickEvent(flipLinks[1]);
            }
            break;

        case '3':  // 3 - Go to the after image
            var flipLinks = $('.flip-link');
            if (flipLinks.length == 3) {
                fireClickEvent(flipLinks[2]);
            }
            break;

        case '?':  // ? - Show help dialog
            $('.dialog-close').click(function() {
                $('#keyboard_shortcuts_dialog').hide();
            });
            $('#keyboard_shortcuts_dialog').show();
            break;
    }
}


$(document).ready(function() {
    $(document).keypress(handleKeyPress);
});
