'use strict';

const { absPath, exists, fail, isDirectory } = require('../vault/common');
const { openVaultUri } = require('./obsidian-open');

function usage() {
  console.error('Usage: open-vault [path]');
  console.error('Opens the current or specified folder as an Obsidian vault.');
}

function parseArgs(argv) {
  if (argv.includes('-h') || argv.includes('--help')) {
    usage();
    process.exit(0);
  }

  if (argv.length > 1) {
    usage();
    fail('open-vault accepts at most one path argument.', 64);
  }

  return { requestedPath: argv[0] || process.cwd() };
}

function main(argv = process.argv.slice(2)) {
  const { requestedPath } = parseArgs(argv);
  const vaultPath = absPath(requestedPath);

  if (!exists(vaultPath)) {
    fail(`vault path does not exist: ${vaultPath}`);
  }

  if (!isDirectory(vaultPath)) {
    fail(`vault path is not a directory: ${vaultPath}`);
  }

  openVaultUri(vaultPath);
}

module.exports = { main };

if (require.main === module) {
  main();
}
