'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail } = require('./command');
const { normalizeRelPath } = require('./selection');

const {
  getVaultKeyFromRoot,
  getManifestPathFromVaultKey,
} = require('../../lib/operation-manifest');

function defaultManifestPath({ root, operation }) {
  const vaultKey = getVaultKeyFromRoot(root);

  return getManifestPathFromVaultKey({
    vaultKey,
    operation,
  });
}

function readJsonFile(filepath, script) {
  try {
    const raw = fs.readFileSync(filepath, 'utf8');
    const data = JSON.parse(raw);
    data.filepath = filepath;
    return data;
  } catch (error) {
    fail(script, `could not read manifest ${filepath}: ${error.message}`);
  }
}

function manifestTimestamp(manifest) {
  return (
    manifest.timestamp ||
    manifest.savedAt ||
    manifest.saved_at ||
    ''
  );
}

function manifestVaultRoot(manifest) {
  if (typeof manifest.vaultRoot === 'string') return manifest.vaultRoot;
  if (typeof manifest.vault_root === 'string') return manifest.vault_root;

  if (
    manifest.vault &&
    typeof manifest.vault === 'object' &&
    typeof manifest.vault.root === 'string'
  ) {
    return manifest.vault.root;
  }

  return '';
}

function assertFreshManifest({ manifest, options, script, queryName }) {
  if (options.allowStaleManifest) return;

  const timestamp = manifestTimestamp(manifest);

  if (!timestamp) {
    fail(script, `manifest has no timestamp; rerun ${queryName} or use --allow-stale-manifest`);
  }

  const thenMs = Date.parse(timestamp);

  if (!Number.isFinite(thenMs)) {
    fail(script, `manifest timestamp is not parseable: ${timestamp}`);
  }

  const ageSeconds = (Date.now() - thenMs) / 1000;

  if (ageSeconds > options.maxAgeSeconds) {
    fail(
      script,
      `manifest is stale: ${Math.round(ageSeconds)}s old; rerun ${queryName} or use --allow-stale-manifest`
    );
  }
}

function getManifest({ options, root, script, operation, queryName }) {
  const filepath = options.manifestPath || defaultManifestPath({ root, operation });

  if (!fs.existsSync(filepath)) {
    fail(script, `${queryName} manifest not found: ${filepath}`);
  }

  const manifest = readJsonFile(filepath, script);

  if (manifest.operation !== operation) {
    fail(script, `manifest operation is ${manifest.operation || 'missing'}, expected ${operation}`);
  }

  const rootFromManifest = manifestVaultRoot(manifest);

  if (rootFromManifest && path.resolve(rootFromManifest) !== path.resolve(root)) {
    fail(
      script,
      [
        'manifest belongs to a different vault:',
        `  manifest: ${rootFromManifest}`,
        `  active:   ${root}`,
      ].join('\n')
    );
  }

  if (!Array.isArray(manifest.items)) {
    fail(script, `${queryName} manifest must contain an items array`);
  }

  assertFreshManifest({ manifest, options, script, queryName });
  return manifest;
}

function uniqueManifestRows({ manifest, script, queryName }) {
  const byPath = new Map();

  for (const row of manifest.items) {
    const relPath = normalizeRelPath(row.path || '');

    if (!relPath) {
      fail(script, `${queryName} manifest item missing path`);
    }

    if (byPath.has(relPath)) {
      fail(script, `${queryName} manifest contains duplicate path: ${relPath}`);
    }

    byPath.set(relPath, {
      ...row,
      path: relPath,
    });
  }

  return [...byPath.values()];
}

module.exports = {
  defaultManifestPath,
  getManifest,
  manifestTimestamp,
  uniqueManifestRows,
};
