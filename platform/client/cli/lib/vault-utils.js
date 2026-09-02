'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { CONTROL_ROOT } = require('../config');

class CliError extends Error {
  constructor(message, code = 1) {
    super(message);
    this.exitCode = code;
  }
}

function fail(message, code = 1) {
  throw new CliError(message, code);
}

function warn(message) {
  console.error(`WARN: ${message}`);
}

function expandHome(value) {
  if (!value) return value;
  if (value === '~') return os.homedir();
  if (value.startsWith('~/')) return path.join(os.homedir(), value.slice(2));
  return value;
}

function absPath(value) {
  return path.resolve(expandHome(value));
}

function exists(p) {
  return fs.existsSync(p);
}

function isDirectory(p) {
  try { return fs.statSync(p).isDirectory(); } catch (_) { return false; }
}

function isRegularFile(p) {
  try { return fs.statSync(p).isFile(); } catch (_) { return false; }
}

function realpathStrict(p, label) {
  try { return fs.realpathSync(p); }
  catch (error) { fail(`could not resolve ${label}: ${p}\n       ${error.message}`); }
}

function findManagedVaultRoot(startInput = '.') {
  const expectedControl = realpathStrict(CONTROL_ROOT, 'Control root');
  let current = absPath(startInput);

  try {
    if (fs.statSync(current).isFile()) current = path.dirname(current);
  } catch (_) {}

  while (true) {
    const obsidianDir = path.join(current, '.obsidian');
    const controlPath = path.join(current, '_control');

    if (isDirectory(obsidianDir)) {
      let linkStat;
      try { linkStat = fs.lstatSync(controlPath); }
      catch (_) {
        fail(`refusing to update unmanaged Obsidian vault:\n       ${current}\n       missing _control symlink`);
      }

      if (!linkStat.isSymbolicLink()) {
        fail(`refusing to update unmanaged Obsidian vault:\n       ${current}\n       _control exists but is not a symlink`);
      }

      const actualControl = realpathStrict(controlPath, '_control symlink');
      if (actualControl !== expectedControl) {
        fail(
          `refusing to update vault with unexpected _control target:\n` +
          `       vault:    ${current}\n` +
          `       actual:   ${actualControl}\n` +
          `       expected: ${expectedControl}`
        );
      }
      return current;
    }

    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }

  fail(`not inside a managed Obsidian vault.\n       No .obsidian directory found above: ${absPath(startInput)}`);
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function gitDirtyGuard(repoRoot, label = 'repository') {
  const gitDir = path.join(repoRoot, '.git');
  if (!exists(gitDir)) {
    warn(`no .git directory found for ${label}; skipping dirty guard: ${repoRoot}`);
    return;
  }

  const result = spawnSync('/usr/bin/git', ['status', '--porcelain'], {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  if (result.error || result.status !== 0) {
    fail(`git dirty guard failed for ${repoRoot}: ${result.error?.message || result.stderr || 'unknown error'}`);
  }

  if (result.stdout.trim() !== '') {
    console.error(`ERROR: refusing to update dirty ${label}:`);
    console.error(`       ${repoRoot}`);
    console.error(`       /usr/bin/git -C ${shellQuote(repoRoot)} status --short`);
    process.exit(2);
  }
}

module.exports = {
  CliError,
  fail,
  warn,
  expandHome,
  absPath,
  exists,
  isDirectory,
  isRegularFile,
  findManagedVaultRoot,
  gitDirtyGuard,
  shellQuote,
};
