'use strict';

const { CliError } = require('./vault/common');

function runCommand(main) {
  Promise.resolve()
    .then(() => main(process.argv.slice(2)))
    .catch((error) => {
      const message = error && error.message ? error.message : String(error);
      console.error(`ERROR: ${message}`);
      process.exit(error instanceof CliError && error.exitCode ? error.exitCode : 1);
    });
}

module.exports = { runCommand };
