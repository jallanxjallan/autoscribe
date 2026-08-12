'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { ensureDir, isDirectory, warn } = require('../vault/common');

const OBSIDIAN_BIN =
  '/home/jeremy/AppImages/Obsidian-1.13.4.AppImage';

function openObsidianUri(uri, { fatal = false } = {}) {
  const logPath = path.join(
    os.homedir(),
    '.cache',
    'open-vault.log',
  );

  ensureDir(path.dirname(logPath));

  const out = fs.openSync(logPath, 'a');
  const err = fs.openSync(logPath, 'a');

  const child = spawn(OBSIDIAN_BIN, [uri], {
    detached: true,
    stdio: ['ignore', out, err],
  });

  child.on('error', (error) => {
    const message =
      `failed to launch ${OBSIDIAN_BIN}: ${error.message}`;

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
  const uri =
    `obsidian://open?path=${encodeURIComponent(target)}`;

  console.error(`Opening Obsidian vault: ${target}`);

  return openObsidianUri(uri, { fatal: true });
}

function openVaultManager(target) {
  openObsidianUri('obsidian://choose-vault');

  console.log('obsidian: opened Vault Manager.');
  console.log("          Use 'Open folder as vault' and select:");
  console.log(`          ${target}`);

  return true;
}

function openVaultFromCreate(target) {
  if (!isDirectory(path.join(target, '.obsidian'))) {
    warn(`cannot open; not an Obsidian vault: ${target}`);
    return false;
  }

  return openVaultUri(target);
}

module.exports = {
  openVaultUri,
  openVaultFromCreate,
};