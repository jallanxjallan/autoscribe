"use strict";

const { loadConfig } = require("./config-loader.js");

function pathsConfig() { return loadConfig("paths"); }

function getNodeRequire() {
  if (typeof require === "function") return require;
  throw new Error("CommonJS require is unavailable in this Obsidian context.");
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;
  if (typeof adapter?.getBasePath === "function") return adapter.getBasePath();
  if (adapter?.basePath) return adapter.basePath;
  throw new Error("Could not determine vault base path.");
}

function getActiveQueryPath(app) {
  const queryPath = app?.workspace?.getActiveFile?.()?.path;
  if (!queryPath) throw new Error("Could not determine active query path.");
  return queryPath;
}

function getControlRoot(queryPath) {
  const marker = `/${String(pathsConfig().query_dir || "queries")}/`;
  const index = String(queryPath || "").indexOf(marker);
  if (index === -1) throw new Error(`Query is not inside a queries folder: ${queryPath}`);
  const root = queryPath.slice(0, index);
  if (!root) throw new Error(`Could not infer control root from query path: ${queryPath}`);
  return root;
}

function cleanRelativePath(relativePath) {
  if (!relativePath || typeof relativePath !== "string") throw new Error("relativePath must be a non-empty string.");
  const path = getNodeRequire()("node:path");
  if (path.isAbsolute(relativePath)) throw new Error(`Expected a control-relative path: ${relativePath}`);
  const parts = relativePath.split(/[\\/]+/).filter(Boolean);
  if (parts.some((part) => part === "..")) throw new Error(`Control-relative path may not contain '..': ${relativePath}`);
  return parts;
}

function toNativePath(path, base, vaultRelativePath) {
  return path.join(base, ...String(vaultRelativePath || "").split("/").filter(Boolean));
}

function createControlLoader({ app, queryPath = null, controlRoot = null } = {}) {
  if (!app) throw new Error("createControlLoader requires app.");
  const nodeRequire = getNodeRequire();
  const path = nodeRequire("node:path");
  const fs = nodeRequire("node:fs");
  const vaultBasePath = getVaultBasePath(app);
  const resolvedQueryPath = queryPath || getActiveQueryPath(app);
  const resolvedControlRoot = controlRoot || getControlRoot(resolvedQueryPath);
  const vaultControlRootPath = toNativePath(path, vaultBasePath, resolvedControlRoot);
  const controlRootPath = fs.realpathSync(vaultControlRootPath);

  function controlPath(relativePath) { return [resolvedControlRoot, relativePath].filter(Boolean).join("/"); }
  function nativePath(vaultRelativePath) { return toNativePath(path, vaultBasePath, vaultRelativePath); }
  function requireControl(relativePath) {
    const fullPath = path.join(controlRootPath, ...cleanRelativePath(relativePath));
    if (nodeRequire.cache?.[fullPath]) delete nodeRequire.cache[fullPath];
    return nodeRequire(fullPath);
  }

  return { nodeRequire, pathMod: path, fsMod: fs, vaultBasePath, queryPath: resolvedQueryPath,
    controlRoot: resolvedControlRoot, vaultControlRootPath, controlRootPath, controlPath, nativePath, requireControl };
}

module.exports = { createControlLoader, getNodeRequire, getVaultBasePath, getActiveQueryPath, getControlRoot, cleanRelativePath, toNativePath };
