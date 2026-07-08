'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const {
  findManagedVaultRoot: findManagedVaultRootStrict,
} = require('../../lib/vault-utils');


class CliError extends Error {
  constructor(message, code = 1) {
    super(message);
    this.exitCode = code;
  }
}


function fail(message, code = 1) {
  throw new CliError(message, code);
}

function warn(message) {
  console.error(`WARN: ${message}`);
}

function expandHome(value) {
  if (!value) return value;
  if (value === '~') return os.homedir();
  if (value.startsWith('~/')) return path.join(os.homedir(), value.slice(2));
  return value;
}

function absPath(value) {
  return path.resolve(expandHome(value));
}

function exists(p) {
  return fs.existsSync(p);
}

function isDirectory(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch (_) {
    return false;
  }
}

function isDirectoryEmpty(dir) {
  return fs.readdirSync(dir).length === 0;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readRequiredEnv(...names) {
  const candidates = names.flat().filter(Boolean);
  for (const name of candidates) {
    const value = process.env[name];
    if (value) return absPath(value);
  }
  fail(`missing required environment variable: ${candidates.join(" or ")}`);
}

function readRequiredEnvPath(...names) {
  return readRequiredEnv(...names);
}

function pathInside(root, candidate) {
  const rel = path.relative(root, candidate);
  return rel && !rel.startsWith('..') && !path.isAbsolute(rel);
}

function isPathInside(child, parent) {
  const rel = path.relative(parent, child);
  return rel === '' || (!!rel && !rel.startsWith('..') && !path.isAbsolute(rel));
}

function relativeDisplay(target, vaultRoot) {
  const rel = path.relative(vaultRoot, target);
  return rel === '' ? 'vault root' : rel;
}

function commandExists(bin) {
  if (bin.includes('/')) {
    try {
      fs.accessSync(bin, fs.constants.X_OK);
      return true;
    } catch (_) {
      return false;
    }
  }

  const result = spawnSync('which', [bin], {
    encoding: 'utf8',
    stdio: 'ignore',
  });

  return result.status === 0;
}

function findManagedVaultRoot(startDir = '.') {
  const start =
    startDir === '.' && process.env.OBSIDIAN_VAULT_ROOT
      ? process.env.OBSIDIAN_VAULT_ROOT
      : startDir;

  return findManagedVaultRootStrict(start);
}

function titleCaseStem(stem) {
  const spaced = String(stem || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!spaced) return 'Untitled';

  return spaced
    .split(' ')
    .map((word) => {
      if (!word) return word;
      if (/^[A-Z0-9]+$/.test(word)) return word;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(' ');
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

module.exports = {
  CliError,
  fail,
  warn,
  expandHome,
  absPath,
  exists,
  isDirectory,
  isDirectoryEmpty,
  ensureDir,
  readRequiredEnv,
  readRequiredEnvPath,
  pathInside,
  isPathInside,
  relativeDisplay,
  commandExists,
  findManagedVaultRoot,
  titleCaseStem,
  shellQuote,
};
