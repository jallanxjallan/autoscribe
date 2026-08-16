const fs = require('fs');
const path = require('path');

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error('This query requires a filesystem-backed Obsidian vault.');
  return root;
}

function autoscribeRoot() {
  return path.join(process.env.HOME || '', '.local/share/autoscribe/obsidian/vaults');
}

function autoscribeVaultDir(app) {
  return path.join(vaultRoot(app), '.autoscribe');
}

function safeReadJson(file, fallback = null) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch { return fallback; }
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

function statInfo(file) {
  try {
    const s = fs.statSync(file);
    return { exists: true, size: s.size, mtime_ms: s.mtimeMs, mtime: s.mtime.toISOString() };
  } catch {
    return { exists: false, size: null, mtime_ms: null, mtime: null };
  }
}

function relpath(root, file) {
  return path.relative(root, file).split(path.sep).join('/');
}

function workflowDir(app, name) {
  return path.join(autoscribeVaultDir(app), 'workflow', name);
}

function selectionsDir(app) {
  return path.join(autoscribeVaultDir(app), 'selections');
}

module.exports = {
  vaultRoot,
  autoscribeRoot,
  autoscribeVaultDir,
  selectionsDir,
  safeReadJson,
  writeJson,
  statInfo,
  relpath,
  workflowDir,
};
