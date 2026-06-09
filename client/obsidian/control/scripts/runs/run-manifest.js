const path = require('path');
const { makeSlug } = require('../lib/slug.js');
const { vaultRoot, writeJson, workflowDir } = require('../lib/vault-state.js');

function promptSlug(item) {
  const slug = String(item?.slug || '').trim();
  if (!slug) {
    const label = item?.path || item?.label || item?.index || 'unknown prompt';
    throw new Error(`Selected prompt is missing a slug: ${label}`);
  }
  return slug;
}

function buildRunManifest({ app, label, selection, plan }) {
  if (!selection || !Array.isArray(selection.items)) throw new Error('A loaded selection is required.');
  if (!plan?.slug) throw new Error('A saved plan with a slug is required.');

  const root = vaultRoot(app);
  const now = new Date().toISOString();
  const cleanLabel = String(label || '').trim() || `${selection.selection_name || 'selection'} + ${plan.label || plan.slug}`;
  const slug = makeSlug('run', cleanLabel);
  const items = selection.items.map((item) => ({
    prompt_slug: promptSlug(item),
    plan_slug: plan.slug,
  }));

  return {
    type: 'run_dispatch_manifest',
    version: 1,
    label: cleanLabel,
    slug,
    created: now,
    updated: now,
    vault: {
      name: path.basename(root),
      root,
    },
    source_selection: {
      path: selection.selection_file,
      name: selection.selection_name,
      mtime: selection.selection_mtime,
      raw_type: selection.raw_type,
    },
    plan: {
      slug: plan.slug,
      label: plan.label || null,
    },
    count: items.length,
    items,
  };
}

function saveRunManifest(app, manifest) {
  const dir = workflowDir(app, 'runs');
  const archiveFile = path.join(dir, `${manifest.slug}.json`);
  const currentFile = path.join(dir, 'current-run.json');
  writeJson(archiveFile, manifest);
  writeJson(currentFile, manifest);
  return { archiveFile, currentFile };
}

module.exports = { buildRunManifest, saveRunManifest };
