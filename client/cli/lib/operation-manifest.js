'use strict';

const path = require('node:path');

function autoscribeHome() {
  return process.env.AUTOSCRIBE_HOME || '';
}

function getVaultKeyFromRoot(root) {
  return path.basename(path.resolve(root))
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'vault';
}

function getVaultAutoscribeDir(root) {
  return path.join(path.resolve(root), '.autoscribe');
}

function operationFilename(operation) {
  const name = String(operation || '').trim();
  return name.endsWith('.json') ? name : `${name}.json`;
}

function getManifestPathForRoot({ root, operation }) {
  return path.join(
    getVaultAutoscribeDir(root),
    'selections',
    operationFilename(operation)
  );
}

function getManifestPathFromVaultKey({ vaultKey, operation }) {
  throw new Error(
    `vault-key manifest lookup is retired (${vaultKey || 'missing'}); pass a vault root and use getManifestPathForRoot()`
  );
}

module.exports = {
  autoscribeHome,
  getVaultKeyFromRoot,
  getVaultAutoscribeDir,
  getManifestPathForRoot,
  getManifestPathFromVaultKey,
};
