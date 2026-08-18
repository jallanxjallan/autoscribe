const fs = require('fs');
const path = require('path');
const os = require('os');
const { loadConfig } = require('./config-loader.js');
function pathsConfig() { return loadConfig('paths'); }
function expandHome(value) { return String(value || '').replace(/^\$HOME(?=\/|$)/, os.homedir()); }

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error('This query requires a filesystem-backed Obsidian vault.');
  return root;
}

function autoscribeRoot() {
  return path.resolve(expandHome(pathsConfig().legacy_state_root));
}

function autoscribeVaultDir(app) {
  return path.join(vaultRoot(app), String(pathsConfig().runtime_dir || '.autoscribe'));
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
  return path.join(autoscribeVaultDir(app), String(pathsConfig().workflow_dir || 'workflow'), name);
}

function selectionsDir(app) {
  return path.join(autoscribeVaultDir(app), String(pathsConfig().selection_dir || 'selections'));
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
