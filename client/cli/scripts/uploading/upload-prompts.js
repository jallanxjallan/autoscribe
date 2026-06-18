'use strict';

const { fail } = require('./command');

function runUploadPrompts() {
  fail(
    'upload-prompts',
    'removed: pipeline input is now rendered and emitted by dispatch-run; use dispatch-run | asc enqueue'
  );
}

module.exports = { main: runUploadPrompts, runUploadPrompts };

if (require.main === module) {
  runUploadPrompts();
}
