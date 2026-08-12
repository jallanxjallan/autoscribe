const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

function vaultRoot(app) {
  const root = app?.vault?.adapter?.basePath;
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

function git(args, cwd) {
  try {
    return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return '';
  }
}

function gitFileState(root, abspath) {
  const rel = relpath(root, abspath);
  const statusText = git(['status', '--porcelain', '--', rel], root);
  const conflicted = statusText.split('\n').some((line) => /^(DD|AU|UD|UA|DU|AA|UU)/.test(line));
  const logText = git(['log', '-n', '1', '--format=%H%x1f%h%x1f%s%x1f%ct', '--', rel], root);
  const [commit = '', shortCommit = '', subject = '', timestamp = ''] = logText ? logText.split('\x1f') : [];
  return {
    repo_state: conflicted ? 'conflicted' : (statusText ? 'dirty' : 'clean'),
    git_status: statusText || '',
    git_commit: commit || null,
    short_commit: shortCommit || (commit ? commit.slice(0, 12) : null),
    git_subject: subject || null,
    git_timestamp: timestamp ? Number(timestamp) : null,
    has_prior_commit: Boolean(commit),
  };
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
  gitFileState,
  workflowDir,
};
