'use strict';

const path = require('node:path');

const CLIENT_ROOT = path.resolve(__dirname);
const OBSIDIAN_ROOT = path.join(CLIENT_ROOT, 'obsidian');

module.exports = Object.freeze({
  CONTROL_ROOT: path.join(OBSIDIAN_ROOT, 'control'),
  CORE_ROOT: path.join(OBSIDIAN_ROOT, 'core'),
  VAULT_REMOTE_NAME: 'origin',
  VAULT_BRANCH: 'main',
  VAULT_BACKUP_ROOT: '/home/jeremy/Dropbox/Repos/obsidian-vaults',
  BARE_REPO_SUFFIX: '.git',
  OBSIDIAN_BIN: '/home/jeremy/AppImages/Obsidian-1.13.4.AppImage',
  OBSIDIAN_OPEN_LOG: '/home/jeremy/.cache/open-vault.log',
});
