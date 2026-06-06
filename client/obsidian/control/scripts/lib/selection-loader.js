const fs = require('fs');
const path = require('path');
const { autoscribeRoot, safeReadJson, statInfo, vaultRoot, relpath, gitFileState } = require('../lib/vault-state.js');

function walkSelectionFiles(root) {
  const out = [];
  try {
    for (const vaultKey of fs.readdirSync(root)) {
      const dir = path.join(root, vaultKey, 'selections');
      if (!fs.existsSync(dir)) continue;
      for (const name of fs.readdirSync(dir)) {
        if (!name.endsWith('.json')) continue;
        const file = path.join(dir, name);
        const s = statInfo(file);
        out.push({ vaultKey, file, name, mtime_ms: s.mtime_ms || 0, mtime: s.mtime });
      }
    }
  } catch {}
  return out.sort((a, b) => b.mtime_ms - a.mtime_ms);
}

function arrayFromSelection(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return [];
  for (const key of ['items', 'records', 'selected', 'selection', 'files', 'prompts']) {
    if (Array.isArray(data[key])) return data[key];
  }
  return [];
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

function normalizePath(root, record) {
  const raw = firstString(
    record.abspath,
    record.absolute_path,
    record.fullpath,
    record.filepath,
    record.file_path,
    record.path,
    record.source_file,
    record.source_path
  );
  if (!raw) return null;
  const expanded = raw.startsWith('~') ? path.join(process.env.HOME || '', raw.slice(1)) : raw;
  return path.isAbsolute(expanded) ? path.normalize(expanded) : path.join(root, expanded);
}

function normalizeRecord(root, record, index) {
  const abspath = normalizePath(root, record);
  const stat = abspath ? statInfo(abspath) : { exists: false };
  const git = abspath && stat.exists ? gitFileState(root, abspath) : {
    repo_state: 'missing', git_status: '', git_commit: null, short_commit: null, has_prior_commit: false,
  };
  const rel = abspath ? relpath(root, abspath) : '';
  return {
    index: index + 1,
    slug: firstString(record.slug, record.uid, record.id, record.prompt_slug),
    label: firstString(record.label, record.title, record.name, record.basename) || (rel ? path.basename(rel, path.extname(rel)) : `Item ${index + 1}`),
    path: rel,
    abspath,
    status: firstString(record.status, record.state),
    stage: firstString(record.stage),
    process: firstString(record.process),
    type: firstString(record.type, record.kind),
    exists: stat.exists,
    size: stat.size || null,
    mtime: stat.mtime || null,
    ...git,
  };
}

function selectionSummary(app, selectionFile) {
  const root = vaultRoot(app);
  const data = safeReadJson(selectionFile, null);
  const rawItems = arrayFromSelection(data);
  const items = rawItems.map((record, index) => normalizeRecord(root, record || {}, index));
  const s = statInfo(selectionFile);
  return {
    selection_file: selectionFile,
    selection_name: path.basename(selectionFile),
    selection_mtime: s.mtime,
    raw_type: data?.type || null,
    count: items.length,
    items,
    warnings: warningsFor(items),
  };
}

function warningsFor(items) {
  const warnings = [];
  const missing = items.filter((i) => !i.exists).length;
  const dirty = items.filter((i) => i.repo_state !== 'clean').length;
  const uncommitted = items.filter((i) => !i.has_prior_commit).length;
  const noSlug = items.filter((i) => !i.slug).length;
  if (missing) warnings.push(`${missing} missing file(s)`);
  if (dirty) warnings.push(`${dirty} dirty repo state item(s)`);
  if (uncommitted) warnings.push(`${uncommitted} item(s) without prior commit`);
  if (noSlug) warnings.push(`${noSlug} item(s) without slug`);
  return warnings;
}

function listSelections(app) {
  return walkSelectionFiles(autoscribeRoot()).map((entry) => {
    const summary = selectionSummary(app, entry.file);
    return { ...entry, count: summary.count, warnings: summary.warnings };
  });
}

module.exports = { listSelections, selectionSummary };
