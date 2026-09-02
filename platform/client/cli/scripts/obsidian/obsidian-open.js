'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { ensureDir, isDirectory, warn } = require('../vault/common');
const { OBSIDIAN_BIN, OBSIDIAN_OPEN_LOG } = require('../../config');

function openObsidianUri(uri, { fatal = false } = {}) {
  ensureDir(path.dirname(OBSIDIAN_OPEN_LOG));
  const out = fs.openSync(OBSIDIAN_OPEN_LOG, 'a');
  const err = fs.openSync(OBSIDIAN_OPEN_LOG, 'a');
  const child = spawn(OBSIDIAN_BIN, [uri], { detached: true, stdio: ['ignore', out, err] });

  child.on('error', (error) => {
    const message = `failed to launch ${OBSIDIAN_BIN}: ${error.message}`;
    if (fatal) {
      console.error(`ERROR: ${message}`);
      process.exitCode = 1;
    } else {
      warn(message);
    }
  });

  child.unref();
  return true;
}

function openVaultUri(target) {
  console.error(`Opening Obsidian vault: ${target}`);
  return openObsidianUri(`obsidian://open?path=${encodeURIComponent(target)}`, { fatal: true });
}

function openVaultFromCreate(target) {
  if (!isDirectory(path.join(target, '.obsidian'))) {
    warn(`cannot open; not an Obsidian vault: ${target}`);
    return false;
  }
  return openVaultUri(target);
}

module.exports = { openVaultUri, openVaultFromCreate };
