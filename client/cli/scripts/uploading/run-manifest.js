'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail } = require('./command');
const { normalizeRelPath } = require('./selection');
function localAutoscribeDir(root) {
  return path.join(path.resolve(root), '.autoscribe');
}

function workflowVaultKey(root) {
  return path.basename(path.resolve(root)).toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function defaultRunManifestPath({ root }) {
  return path.join(
    localAutoscribeDir(root),
    'workflow',
    'runs',
    'current-run.json'
  );
}

function readRunManifest(filepath, script) {
  try {
    const raw = fs.readFileSync(filepath, 'utf8');
    const manifest = JSON.parse(raw);
    manifest.filepath = filepath;
    return manifest;
  } catch (error) {
    fail(script, `could not read run manifest ${filepath}: ${error.message}`);
  }
}

function writeRunManifest(filepath, manifest, script) {
  try {
    const clean = { ...manifest };
    delete clean.filepath;
    clean.updated = new Date().toISOString();
    fs.writeFileSync(filepath, `${JSON.stringify(clean, null, 2)}\n`, 'utf8');
  } catch (error) {
    fail(script, `could not write run manifest ${filepath}: ${error.message}`);
  }
}

function manifestVaultRoot(manifest) {
  if (typeof manifest.vault_root === 'string') return manifest.vault_root;
  if (typeof manifest.vaultRoot === 'string') return manifest.vaultRoot;
  if (manifest.vault && typeof manifest.vault.root === 'string') return manifest.vault.root;
  return '';
}

function assertRunManifest({ manifest, root, script }) {
  if (manifest.type !== 'run_manifest') {
    fail(script, `manifest type is ${manifest.type || 'missing'}, expected run_manifest`);
  }

  const manifestRoot = manifestVaultRoot(manifest);
  if (manifestRoot && path.resolve(manifestRoot) !== path.resolve(root)) {
    fail(
      script,
      [
        'run manifest belongs to a different vault:',
        `  manifest: ${manifestRoot}`,
        `  active:   ${root}`,
      ].join('\n')
    );
  }

  if (!Array.isArray(manifest.calls)) {
    fail(script, 'run manifest must contain a calls array');
  }
}

function loadRunManifest({ options, root, script }) {
  const filepath = options.manifestPath || defaultRunManifestPath({ root });

  if (!fs.existsSync(filepath)) {
    fail(script, `run manifest not found: ${filepath}`);
  }

  const manifest = readRunManifest(filepath, script);
  assertRunManifest({ manifest, root, script });
  return manifest;
}

function pendingRunCalls(manifest) {
  return manifest.calls
    .filter((call) => String(call.upload_status || 'pending') === 'pending')
    .map((call) => ({
      ...call,
      path: normalizeRelPath(call.path || call.filepath || call.prompt?.path || ''),
    }));
}

function markCallUploaded({ manifest, call, uploadedAt }) {
  const index = manifest.calls.findIndex((item) => {
    if (call.index !== undefined && item.index === call.index) return true;
    if (call.call_slug && item.call_slug === call.call_slug) return true;
    return false;
  });

  if (index < 0) return;

  manifest.calls[index] = {
    ...manifest.calls[index],
    upload_status: 'uploaded',
    uploaded_at: uploadedAt,
    upload_error: null,
  };
}

function markCallUploadError({ manifest, call, error }) {
  const index = manifest.calls.findIndex((item) => {
    if (call.index !== undefined && item.index === call.index) return true;
    if (call.call_slug && item.call_slug === call.call_slug) return true;
    return false;
  });

  if (index < 0) return;

  manifest.calls[index] = {
    ...manifest.calls[index],
    upload_status: 'error',
    upload_error: error.message || String(error),
  };
}

module.exports = {
  defaultRunManifestPath,
  workflowVaultKey,
  localAutoscribeDir,
  loadRunManifest,
  markCallUploaded,
  markCallUploadError,
  pendingRunCalls,
  writeRunManifest,
};
