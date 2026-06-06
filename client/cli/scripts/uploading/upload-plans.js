'use strict';

const { runUploadControlComponent } = require('./upload-control-component');

function runUploadPlans(config = {}) {
  runUploadControlComponent({
    componentName: 'plans',
    script: config.script || 'upload-plans',
    defaults: config.defaults,
  });
}

module.exports = { runUploadPlans };

if (require.main === module) {
  runUploadPlans();
}
