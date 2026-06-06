'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail } = require('./command');

function normalizeRelPath(relPath) {
  return String(relPath || '')
    .replace(/\\/g, '/')
    .replace(/^\.\//, '')
    .replace(/^\/+/, '');
}

function vaultPath(root, relPath) {
  return path.join(root, ...normalizeRelPath(relPath).split('/'));
}

function readVaultFile(root, relPath) {
  return fs.readFileSync(vaultPath(root, relPath), 'utf8');
}

function vaultFileExists(root, relPath) {
  const fullPath = vaultPath(root, relPath);
  return fs.existsSync(fullPath) && fs.statSync(fullPath).isFile();
}

function assertVaultRoot({ root, script }) {
  if (!root) fail(script, 'could not resolve git root');

  const obsidianDir = path.join(root, '.obsidian');
  if (!fs.existsSync(obsidianDir) || !fs.statSync(obsidianDir).isDirectory()) {
    fail(script, `git root is not an Obsidian vault: ${root}`);
  }

  const controlPath = path.join(root, '_control');
  if (!fs.existsSync(controlPath)) {
    fail(script, `refusing to run without _control in vault root: ${root}`);
  }
}

module.exports = {
  assertVaultRoot,
  normalizeRelPath,
  readVaultFile,
  vaultFileExists,
  vaultPath,
};
