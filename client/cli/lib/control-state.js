'use strict';

const fs = require('node:fs');
const path = require('node:path');

const STATE_RELATIVE_PATH = path.join('.locals.autoscribe', 'control-upload-state.json');

function controlStatePath(vaultRoot) {
  if (!vaultRoot) throw new Error('controlStatePath requires vaultRoot.');
  return path.join(vaultRoot, STATE_RELATIVE_PATH);
}

function emptyState() {
  return {
    type: 'autoscribe.local-control-upload-state',
    version: 1,
    updated_at: '',
    controls: {},
  };
}

function readControlState(vaultRoot) {
  const filepath = controlStatePath(vaultRoot);

  if (!fs.existsSync(filepath)) {
    return emptyState();
  }

  const parsed = JSON.parse(fs.readFileSync(filepath, 'utf8'));

  return {
    ...emptyState(),
    ...parsed,
    controls: parsed && typeof parsed.controls === 'object' && !Array.isArray(parsed.controls)
      ? parsed.controls
      : {},
  };
}

function writeControlState(vaultRoot, state) {
  const filepath = controlStatePath(vaultRoot);
  const next = {
    ...emptyState(),
    ...state,
    updated_at: new Date().toISOString(),
    controls: state && typeof state.controls === 'object' && !Array.isArray(state.controls)
      ? state.controls
      : {},
  };

  fs.mkdirSync(path.dirname(filepath), { recursive: true });
  fs.writeFileSync(filepath, `${JSON.stringify(next, null, 2)}\n`, 'utf8');
  return filepath;
}

function stateKeyForControl(control) {
  if (!control) return '';
  return control.path || control.slug || '';
}

function staleLocalControls({ vaultRoot, controls }) {
  const state = readControlState(vaultRoot);
  const stale = [];

  for (const control of controls || []) {
    if (!control || control.scope !== 'vault') continue;

    const key = stateKeyForControl(control);
    const previous = state.controls[key];

    if (!previous) {
      stale.push({ control, reason: 'missing upload-state record' });
      continue;
    }

    if (previous.slug !== control.slug) {
      stale.push({ control, reason: `slug changed (${previous.slug || 'missing'} -> ${control.slug})` });
      continue;
    }

    if (previous.content_sha256 !== control.content_sha256) {
      stale.push({ control, reason: 'content hash changed' });
    }
  }

  return stale;
}

function markControlsUploaded({ vaultRoot, controls, uploadedAt = new Date().toISOString() }) {
  const state = readControlState(vaultRoot);

  for (const control of controls || []) {
    if (!control || control.scope !== 'vault') continue;
    const key = stateKeyForControl(control);
    if (!key) continue;

    state.controls[key] = {
      slug: control.slug,
      family: control.family,
      type: control.type || '',
      path: control.path || '',
      content_sha256: control.content_sha256,
      uploaded_at: uploadedAt,
    };
  }

  return writeControlState(vaultRoot, state);
}

module.exports = {
  STATE_RELATIVE_PATH,
  controlStatePath,
  readControlState,
  writeControlState,
  staleLocalControls,
  markControlsUploaded,
};
