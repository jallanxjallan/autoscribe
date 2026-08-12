const fs = require('fs');
const path = require('path');
const {
  vaultRoot,
  selectionsDir,
  safeReadJson,
  statInfo,
  gitFileState,
} = require('../lib/vault-state.js');

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function candidateItems(data) {
  for (const key of ['items', 'records', 'selected', 'files', 'prompts']) {
    if (Array.isArray(data?.[key])) return data[key];
  }

  for (const key of [
    ['selection', 'items'],
    ['selection', 'rows'],
    ['selection', 'selected'],
    ['selection', 'selectedItems'],
    ['selection', 'selected_items'],
    ['selection', 'selectedRows'],
    ['selection', 'selected_rows'],
    ['saved_selection', 'items'],
    ['saved_selection', 'rows'],
    ['saved_selection', 'selected'],
  ]) {
    const value = key.reduce((obj, part) => obj && obj[part], data);
    if (Array.isArray(value)) return value;
  }

  const paths = Array.isArray(data?.paths) ? data.paths : [];
  const slugs = Array.isArray(data?.slugs) ? data.slugs : [];
  const count = Math.max(paths.length, slugs.length);
  if (count) {
    return Array.from({ length: count }, (_unused, index) => ({
      path: paths[index] || '',
      slug: slugs[index] || '',
    }));
  }

  return [];
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

function normalizeItem(app, item, index) {
  const root = vaultRoot(app);
  const rel = firstString(item.path, item.file, item.filepath, item.vault_path, item.vaultPath);
  const abspath = firstString(item.abspath, item.absolute_path, item.absolutePath) || (rel ? path.join(root, rel) : '');
  const stat = abspath ? statInfo(abspath) : { exists: false, size: null, mtime: null };
  const gitState = abspath && stat.exists
    ? gitFileState(root, abspath)
    : { repo_state: 'missing', git_status: '', git_commit: null, short_commit: null, has_prior_commit: false };

  return {
    index: item.index || index + 1,
    label: firstString(item.label, item.title, item.name) || (rel ? path.basename(rel) : `Item ${index + 1}`),
    slug: firstString(item.slug, item.prompt_slug, item.call_slug),
    path: rel,
    abspath,
    type: item.type || item.class || null,
    status: item.status || null,
    stage: item.stage || null,
    process: item.process || null,
    exists: stat.exists,
    size: stat.size,
    mtime: stat.mtime,
    ...gitState,
    raw: item,
  };
}

function selectionSummary(app, selectionFile) {
  const data = safeReadJson(selectionFile, null);
  const s = statInfo(selectionFile);
  const rawItems = candidateItems(data);
  const items = rawItems.map((item, index) => normalizeItem(app, item, index));
  const warnings = [];

  const missing = items.filter((item) => !item.exists).length;
  if (missing) warnings.push(`${missing} missing file${missing === 1 ? '' : 's'}`);

  const dirty = items.filter((item) => item.repo_state === 'dirty').length;
  if (dirty) warnings.push(`${dirty} dirty file${dirty === 1 ? '' : 's'}`);

  return {
    selection_file: selectionFile,
    selection_name: path.basename(selectionFile),
    selection_mtime: s.mtime,
    raw_type: data?.type || data?.recordType || null,
    vaultKey: data?.vaultKey || data?.vault_info?.key || path.basename(vaultRoot(app)),
    count: items.length,
    warnings,
    items,
    raw: data,
  };
}

function currentSelectionSummary(app, data, selectionFile = '') {
  const rawItems = candidateItems(data);
  const items = rawItems.map((item, index) => normalizeItem(app, item, index));
  const warnings = [];
  const missing = items.filter((item) => !item.exists).length;
  if (missing) warnings.push(`${missing} missing file${missing === 1 ? '' : 's'}`);
  const dirty = items.filter((item) => item.repo_state === 'dirty').length;
  if (dirty) warnings.push(`${dirty} dirty file${dirty === 1 ? '' : 's'}`);
  return {
    selection_file: selectionFile,
    selection_name: 'current-selection',
    selection_mtime: data?.updated_at || null,
    raw_type: data?.type || data?.recordType || null,
    vaultKey: data?.vault_key || path.basename(vaultRoot(app)),
    count: items.length,
    warnings,
    items,
    raw: data,
  };
}

function listSelections(app) {
  const dir = selectionsDir(app);
  if (!fs.existsSync(dir)) return [];

  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => {
      const file = path.join(dir, entry.name);
      const summary = selectionSummary(app, file);
      const stat = statInfo(file);
      return {
        file,
        name: entry.name,
        vaultKey: summary.vaultKey,
        count: summary.count,
        warnings: summary.warnings,
        mtime: stat.mtime,
        mtime_ms: stat.mtime_ms || 0,
      };
    })
    .sort((a, b) => b.mtime_ms - a.mtime_ms);
}

module.exports = { currentSelectionSummary, listSelections, selectionSummary };
