'use strict';

const { runUploadControlComponent } = require('./upload-control-component');

function runUploadInstructions(config = {}) {
  runUploadControlComponent({
    componentName: 'instructions',
    script: config.script || 'upload-instructions',
    defaults: config.defaults,
  });
}

module.exports = { runUploadInstructions };

if (require.main === module) {
  runUploadInstructions();
}
