var fs = require('fs');
var system = require('system');


// Read and validate config.
var configPath = null;
if (system.args.length == 2) {
  configPath = system.args[1];
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

['targetUrl', 'outputPath'].forEach(function(field) {
  if (!config[field]) {
    console.log('Missing required field: ' + field);
    phantom.exit(1);
  }
});

// Screenshot the page.
var page = require('webpage').create();
if (config.viewportSize) {
  page.viewportSize = {
    width: config.viewportSize.width,
    height: config.viewportSize.height
  };
}

page.open(config.targetUrl, function(status) {
  // Inject code
  // Wait for completion
  // Check status
  page.render(config.outputPath);
  phantom.exit(0);
});
