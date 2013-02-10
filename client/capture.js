var fs = require('fs');
var system = require('system');


// Read and validate config.
var configPath = null;
var outputPath = null;
if (system.args.length == 3) {
  configPath = system.args[1];
  outputPath = system.args[2];
} else {
  console.log('Usage: phantomjs capture.js <config.js>');
  phantom.exit(1);
}

try {
  var config = JSON.parse(fs.read(configPath));
} catch (e) {
  console.log('Could not read config at "' + configPath + '":\n' + e);
  phantom.exit(1);
}

['targetUrl'].forEach(function(field) {
  if (!config[field]) {
    console.log('Missing required field: ' + field);
    phantom.exit(1);
  }
});

// Configure the page.
var page = require('webpage').create();
if (config.viewportSize) {
  page.viewportSize = {
    width: config.viewportSize.width,
    height: config.viewportSize.height
  };
}

// TODO: Custom headers
// TODO: Path to code to inject
// TODO: Username/password using HTTP basic auth
// TODO: Header key/value pairs
// TODO: CSS selectors to hide
// TODO: User agent spoofing shortcut


// Screenshot
page.open(config.targetUrl, function(status) {
  // Inject code
  // Wait for completion
  // Check status
  page.render(outputPath);
  phantom.exit(0);
});
