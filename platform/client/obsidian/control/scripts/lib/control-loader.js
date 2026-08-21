"use strict";

const { getNodeRequire } = require("./node-runtime.js");
const { requireVaultBasePath } = require("./vault-paths.js");
const { loadConfig } = require("./config-loader.js");

function pathsConfig() { return loadConfig("paths"); }

function getVaultBasePath(app) {
  return requireVaultBasePath(app);
}

function getActiveQueryPath(app) {
  const activeFile = app?.workspace?.getActiveFile?.();
  const queryPath = activeFile?.path;
  if (!queryPath) throw new Error("Could not determine active query path.");
  return queryPath;
}

function getControlRoot(queryPath) {
  const marker = `/${String(pathsConfig().query_dir || "queries")}/`;
  const markerIndex = String(queryPath || "").indexOf(marker);
  if (markerIndex === -1) throw new Error(`Query is not inside a queries folder: ${queryPath}`);
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

  // Filesystem access here is package loading only: resolve the shared _control
  // symlink to its physical code directory. Workflow discovery belongs to svc.
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

module.exports = {
  createControlLoader,
  getNodeRequire,
  getVaultBasePath,
  getActiveQueryPath,
  getControlRoot,
  cleanRelativePath,
  toNativePath,
};
