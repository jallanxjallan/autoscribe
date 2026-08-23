"use strict";

// This file is the one permitted bootstrap across the Obsidian/Electron ->
// Control boundary. Keep it self-contained: do not import other Control modules
// at top level, because their cache must be cleared before they are touched.
function getNodeRequire() {
  if (typeof require === "function") return require;
  if (typeof window !== "undefined" && typeof window.require === "function") {
    return window.require;
  }
  throw new Error("Node require is unavailable in this Obsidian context.");
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;
  const base = typeof adapter?.getBasePath === "function"
    ? adapter.getBasePath()
    : adapter?.basePath;
  if (!base) throw new Error("Could not determine vault base path.");
  return base;
}

function getActiveQueryPath(app) {
  const queryPath = app?.workspace?.getActiveFile?.()?.path;
  if (!queryPath) throw new Error("Could not determine active query path.");
  return queryPath;
}

function getControlRoot(queryPath) {
  const nodeRequire = getNodeRequire();
  const pathMod = nodeRequire("node:path");
  const normalized = String(queryPath || "").replace(/\\/g, "/");
  if (!normalized || !normalized.includes("/")) {
    throw new Error(`Query has no parent directory: ${queryPath}`);
  }
  // Query notes live one directory below the Control root. Infer from structure
  // rather than hard-coding config.paths.query_dir, so renaming that directory
  // does not require changing bootstrap JavaScript.
  const queryDirPath = pathMod.posix.dirname(normalized);
  const controlRoot = pathMod.posix.dirname(queryDirPath);
  if (!controlRoot || controlRoot === ".") {
    throw new Error(`Could not infer control root from query path: ${queryPath}`);
  }
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
  const vaultBasePath = pathMod.resolve(getVaultBasePath(app));
  const resolvedQueryPath = queryPath || (controlRoot ? null : getActiveQueryPath(app));
  const resolvedControlRoot = controlRoot || getControlRoot(resolvedQueryPath);
  const vaultControlRootPath = toNativePath(pathMod, vaultBasePath, resolvedControlRoot);

  // _control may be a symlink into the installed Control package. Node caches
  // modules under their physical filenames, so resolve it before invalidating.
  const controlRootPath = fsMod.realpathSync(vaultControlRootPath);

  // Electron keeps Node modules alive for the renderer lifetime. Clear the
  // entire Control package once at entry so edits, moves and deleted files can
  // never survive into a new macro/query invocation.
  for (const id of Object.keys(nodeRequire.cache || {})) {
    if (id === controlRootPath || id.startsWith(`${controlRootPath}${pathMod.sep}`)) {
      delete nodeRequire.cache[id];
    }
  }

  function controlPath(relativePath) {
    return [resolvedControlRoot, relativePath].filter(Boolean).join("/");
  }

  function nativePath(vaultRelativePath) {
    return toNativePath(pathMod, vaultBasePath, vaultRelativePath);
  }

  function requireControl(relativePath) {
    const fullPath = pathMod.join(controlRootPath, ...cleanRelativePath(relativePath));
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

module.exports = {
  createControlLoader,
  getNodeRequire,
  getVaultBasePath,
  getActiveQueryPath,
  getControlRoot,
  cleanRelativePath,
  toNativePath,
};
