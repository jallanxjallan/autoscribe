'use strict';

const fs = require('node:fs');
const {
  CliError,
  fail,
  warn,
  absPath,
  exists,
  isDirectory,
  findManagedVaultRoot,
  shellQuote,
} = require('../../lib/vault-utils');

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

module.exports = {
  CliError,
  fail,
  warn,
  absPath,
  exists,
  isDirectory,
  ensureDir,
  findManagedVaultRoot,
  shellQuote,
};
