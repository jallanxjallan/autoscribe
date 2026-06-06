'use strict';

const { runEnqueuePrompts } = require('./enqueue-prompts');

function main() {
  return runEnqueuePrompts({ script: 'enqueue-prompts' });
}

module.exports = { main };

if (require.main === module) {
  main();
}
