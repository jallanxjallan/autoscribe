'use strict';

const { runUploadControlComponent } = require('./upload-control-component');

function runUploadDrivers(config = {}) {
  runUploadControlComponent({
    componentName: 'drivers',
    script: config.script || 'upload-drivers',
    defaults: config.defaults,
  });
}

module.exports = { runUploadDrivers };

if (require.main === module) {
  runUploadDrivers();
}
