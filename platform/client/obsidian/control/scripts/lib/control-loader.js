"use strict";

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");
const { vaultRoot, statInfo, relpath } = require("./vault-state.js");
const { loadConfig } = require("./config-loader.js");
function pathsConfig() { return loadConfig("paths"); }
function workflowConfig() { return loadConfig("workflow"); }
function expandHome(value) { return String(value || "").replace(/^\$HOME(?=\/|$)/, os.homedir()); }


function getNodeRequire() {
  if (typeof require === "function") return require;
  if (typeof window !== "undefined" && typeof window.require === "function") return window.require;
  throw new Error("Node require is unavailable in this Obsidian context.");
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;

  if (typeof adapter?.getBasePath === "function") {
    return adapter.getBasePath();
  }

  if (adapter?.basePath) {
    return adapter.basePath;
  }

  throw new Error("Could not determine vault base path.");
}

function getActiveQueryPath(app) {
  const activeFile = app?.workspace?.getActiveFile?.();
  const queryPath = activeFile?.path;

  if (!queryPath) {
    throw new Error("Could not determine active query path.");
  }

  return queryPath;
}

function getControlRoot(queryPath) {
  const marker = `/${String(pathsConfig().query_dir || "queries")}/`;
  const markerIndex = String(queryPath || "").indexOf(marker);

  if (markerIndex === -1) {
    throw new Error(`Query is not inside a queries folder: ${queryPath}`);
  }

  const controlRoot = queryPath.slice(0, markerIndex);
  if (!controlRoot) throw new Error(`Could not infer control root from query path: ${queryPath}`);
  return controlRoot;
}

function cleanRelativePath(relativePath) {
  if (!relativePath || typeof relativePath !== "string") {
    throw new Error("relativePath must be a non-empty string.");
  }

  const nodeRequire = getNodeRequire();
  const pathMod = nodeRequire("node:path");

  if (pathMod.isAbsolute(relativePath)) {
    throw new Error(`Expected a control-relative path, not absolute path: ${relativePath}`);
  }

  const parts = relativePath.split(/[\\/]+/).filter(Boolean);
  if (parts.some((part) => part === "..")) {
    throw new Error(`Control-relative path may not contain '..': ${relativePath}`);
  }

  return parts;
}

function toNativePath(pathMod, base, vaultRelativePath) {
  return pathMod.join(base, ...String(vaultRelativePath || "").split("/").filter(Boolean));
}

function createControlLoader({ app, queryPath = null, controlRoot = null } = {}) {
  if (!app) throw new Error("createControlLoader requires app.");

  const nodeRequire = getNodeRequire();
  const pathMod = nodeRequire("node:path");
  const fsMod = nodeRequire("node:fs");

  const vaultBasePath = getVaultBasePath(app);
  const resolvedQueryPath = queryPath || getActiveQueryPath(app);
  const resolvedControlRoot = controlRoot || getControlRoot(resolvedQueryPath);

  const vaultControlRootPath = toNativePath(pathMod, vaultBasePath, resolvedControlRoot);
  const controlRootPath = fsMod.realpathSync(vaultControlRootPath);

  function controlPath(relativePath) {
    return [resolvedControlRoot, relativePath].filter(Boolean).join("/");
  }

  function nativePath(vaultRelativePath) {
    return toNativePath(pathMod, vaultBasePath, vaultRelativePath);
  }

  function requireControl(relativePath) {
    const fullPath = pathMod.join(controlRootPath, ...cleanRelativePath(relativePath));
    if (nodeRequire.cache?.[fullPath]) delete nodeRequire.cache[fullPath];
    return nodeRequire(fullPath);
  }

  return {
    nodeRequire,
    pathMod,
    fsMod,
    vaultBasePath,
    queryPath: resolvedQueryPath,
    controlRoot: resolvedControlRoot,
    vaultControlRootPath,
    controlRootPath,
    controlPath,
    nativePath,
    requireControl,
  };
}


function skipDirs() { return new Set(pathsConfig().skip_dirs || []); }
function defaultLibraryVault() { return expandHome(pathsConfig().library_vault); }

function uniqueExistingRoots(roots) {
  const seen = new Set();
  const out = [];
  for (const root of roots) {
    if (!root) continue;
    const resolved = path.resolve(root);
    if (seen.has(resolved)) continue;
    try {
      if (!fs.statSync(resolved).isDirectory()) continue;
    } catch {
      continue;
    }
    seen.add(resolved);
    out.push(resolved);
  }
  return out;
}

function controlRoots(app) {
  const active = vaultRoot(app);
  return uniqueExistingRoots([
    active,
    process.env[String(pathsConfig().environment?.library_vault || "AUTOSCRIBE_LIBRARY_VAULT")],
    defaultLibraryVault(),
  ]);
}

function ascCandidatePaths() {
  const envName = String(pathsConfig().environment?.asc_bin || "ASC_BIN");
  return [
    process.env[envName],
    ...(pathsConfig().asc_candidate_paths || []).map(expandHome),
  ].filter(Boolean);
}

function findAscCommand() {
  for (const candidate of ascCandidatePaths()) {
    if (fs.existsSync(candidate)) return { command: candidate, via: 'path' };
  }

  for (const shell of (pathsConfig().shell_candidates || [])) {
    if (!fs.existsSync(shell)) continue;
    const result = spawnSync(shell, ['-lc', 'command -v asc'], { encoding: 'utf8' });
    const found = String(result.stdout || '').trim().split(/\r?\n/)[0];
    if (result.status === 0 && found) return { command: found, via: shell };
  }

  return { command: process.env[String(pathsConfig().environment?.asc_bin || "ASC_BIN")] || String(pathsConfig().asc_command || "asc"), via: "unresolved" };
}

function loadAscSnapshot({ args, expectedType, label }) {
  const resolved = findAscCommand();
  const result = spawnSync(resolved.command, args, {
    encoding: 'utf8',
    maxBuffer: Number(workflowConfig().control_loader?.asc_snapshot_max_buffer_bytes || 10485760),
  });

  const command = resolved.command;
  const stdout = String(result.stdout || '').trim();
  const stderr = String(result.stderr || '').trim();

  if (result.error) {
    return {
      data: null,
      command,
      args,
      error: `${result.error.message}; tried ASC_BIN, ~/Python3.13Env/bin/asc, ~/.local/bin/asc, /usr/local/bin/asc, /usr/bin/asc, and shell command -v asc`,
      stderr,
      stdout,
    };
  }

  if (result.status !== 0) {
    return {
      data: null,
      command,
      args,
      error: `asc ${args.join(' ')} exited with status ${result.status}`,
      stderr,
      stdout,
    };
  }

  try {
    let records;
    try {
      const parsed = JSON.parse(stdout);
      records = Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      records = stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => JSON.parse(line));
    }
    const data = records.find((record) => record?.type === expectedType);
    if (!data || !data.registries) {
      return {
        data: null,
        command,
        args,
        error: `asc ${args.join(' ')} did not return a ${expectedType} NDJSON record.`,
        stderr,
        stdout,
      };
    }
    return { data, command, args, error: null, stderr, stdout: '' };
  } catch (err) {
    return {
      data: null,
      command,
      args,
      error: `Could not parse ${label} NDJSON: ${err.message}`,
      stderr,
      stdout,
    };
  }
}

function loadNamedSnapshot(name) {
  const spec = loadConfig("protocol").asc_snapshots?.[name] || {};
  return loadAscSnapshot({
    args: [String(spec.command || name), String(spec.subcommand || "snapshot")],
    expectedType: String(spec.expected_type || ""),
    label: String(spec.label || `${name} snapshot`),
  });
}

function loadRegistrySnapshot() { return loadNamedSnapshot("registry"); }
function loadControlSnapshot() { return loadNamedSnapshot("control"); }

function snapshotList(snapshot, name) {
  return Object.entries(snapshot?.registries?.[name] || {}).map(([registryKey, value]) => {
    const record = value && typeof value === 'object' && !Array.isArray(value)
      ? { ...value }
      : { value };
    return {
      ...record,
      registry_key: registryKey,
      key: firstString(record.key, record.slug, record.record_identity, registryKey),
    };
  });
}

function walkMarkdown(root, dir = root, out = []) {
  let entries = [];
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const entry of entries) {
    if (entry.name.startsWith('.') && skipDirs().has(entry.name)) continue;
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!skipDirs().has(entry.name)) walkMarkdown(root, file, out);
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      out.push(file);
    }
  }
  return out;
}

function parseFrontmatter(text) {
  const m = /^---\s*\n([\s\S]*?)\n---\s*/.exec(text || '');
  if (!m) return {};
  const out = {};
  for (const line of m[1].split(/\r?\n/)) {
    const mm = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
    if (!mm) continue;
    const key = mm[1];
    let value = mm[2].trim();
    value = value.replace(/^[\'\"]|[\'\"]$/g, '');
    out[key] = value;
  }
  return out;
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

function readInstructionFile(root, file, source) {
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { return null; }
  const fm = parseFrontmatter(text);
  const slug = firstString(fm.slug, fm.uid, fm.id);
  if (!slug || !/^ins\./.test(slug)) return null;
  const kind = 'instruction';
  const stat = statInfo(file);
  const rel = relpath(root, file);
  return {
    kind,
    slug,
    label: firstString(fm.label, fm.title, fm.name) || path.basename(file, '.md'),
    source,
    root,
    path: rel,
    abspath: file,
    exists: stat.exists,
    size: stat.size,
    mtime: stat.mtime,
    repo_state: 'service-managed',
    git_status: '',
    git_commit: null,
    short_commit: null,
    has_prior_commit: null,
  };
}

function rootSourceName(activeRoot, root) {
  if (path.resolve(activeRoot) === path.resolve(root)) return 'active';
  if (path.basename(root).toLowerCase() === 'instructions') return 'library';
  return path.basename(root) || 'control';
}

function listInstructions(app) {
  const activeRoot = vaultRoot(app);
  const records = [];
  for (const root of controlRoots(app)) {
    const source = rootSourceName(activeRoot, root);
    for (const file of walkMarkdown(root)) {
      const record = readInstructionFile(root, file, source);
      if (record) records.push(record);
    }
  }

  const bySlug = new Map();
  for (const record of records) {
    const prior = bySlug.get(record.slug);
    if (!prior || (prior.source !== 'active' && record.source === 'active')) {
      bySlug.set(record.slug, record);
    }
  }

  const instructions = Array.from(bySlug.values());
  instructions.sort((a, b) =>
    a.source.localeCompare(b.source) ||
    a.label.localeCompare(b.label) ||
    a.slug.localeCompare(b.slug)
  );
  return instructions;
}

function listControls(app) {
  return listInstructions(app);
}

function controlWarnings(records) {
  const warnings = [];
  const dirty = records.filter((r) => r.repo_state && r.repo_state !== 'clean').length;
  const missingCommit = records.filter((r) => r.has_prior_commit === false).length;
  if (dirty) warnings.push(`${dirty} selected control file(s) are dirty`);
  if (missingCommit) warnings.push(`${missingCommit} selected control file(s) have no prior commit`);
  return warnings;
}

module.exports = {
  createControlLoader,
  getNodeRequire,
  getVaultBasePath,
  getActiveQueryPath,
  getControlRoot,
  cleanRelativePath,
  toNativePath,
  listInstructions,
  listControls,
  controlWarnings,
  controlRoots,
  loadRegistrySnapshot,
  loadControlSnapshot,
  snapshotList,
};
