'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { commandExists, ensureDir, isDirectory, warn } = require('../vault/common');

function openVaultUri(target) {
  const opener = process.env.OBSIDIAN_OPEN_BIN || process.env._OBSIDIAN_OPEN_BIN || 'xdg-open';
  const uri = `obsidian://open?path=${encodeURIComponent(target)}`;
  const logPath = path.join(os.homedir(), '.cache', 'open-vault.log');

  ensureDir(path.dirname(logPath));

  const out = fs.openSync(logPath, 'a');
  const err = fs.openSync(logPath, 'a');

  console.error(`Opening Obsidian vault: ${target}`);

  const child = spawn(opener, [uri], {
    detached: true,
    stdio: ['ignore', out, err],
  });

  child.on('error', (error) => {
    console.error(`ERROR: failed to launch ${opener}: ${error.message}`);
    process.exit(1);
  });

  child.unref();
}

function openVaultManager(target) {
  const opener = process.env.OBSIDIAN_OPEN_BIN || process.env._OBSIDIAN_OPEN_BIN || 'xdg-open';

  if (!commandExists(opener)) {
    warn(`could not open Obsidian Vault Manager; ${opener} not found.`);
    return false;
  }

  const logPath = path.join(os.homedir(), '.cache', 'open-vault.log');
  ensureDir(path.dirname(logPath));

  const out = fs.openSync(logPath, 'a');
  const err = fs.openSync(logPath, 'a');

  const child = spawn(opener, ['obsidian://choose-vault'], {
    detached: true,
    stdio: ['ignore', out, err],
  });

  child.on('error', (error) => {
    warn(`failed to launch ${opener}: ${error.message}`);
  });

  child.unref();

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

  const obsidianBin = process.env.OBSIDIAN_APP_BIN || process.env._OBSIDIAN_BIN || 'obsidian';

  if (commandExists(obsidianBin)) {
    const result = spawnSync(obsidianBin, ['vault'], {
      cwd: target,
      encoding: 'utf8',
      stdio: 'ignore',
    });

    if (result.status === 0) {
      console.log('obsidian: opened/recognized vault via CLI');
      return true;
    }

    warn('Obsidian CLI did not open the new vault from cwd.');
  } else {
    warn('obsidian command not found on PATH.');
  }

  return openVaultManager(target);
}

module.exports = {
  openVaultUri,
  openVaultFromCreate,
};
