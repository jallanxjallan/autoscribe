"use strict";

const { getNodeRequire } = require("./node-runtime.js");
const { requireVaultBasePath } = require("./vault-paths.js");

function getVaultBasePath(app) {
  return requireVaultBasePath(app);
}

function getVaultName(app) {
  return String(app?.vault?.getName?.() || app?.vault?.name || "vault").trim() || "vault";
}

function getActiveQueryPath(app) {
  const queryPath = app?.workspace?.getActiveFile?.()?.path;
  if (!queryPath) throw new Error("Could not determine active query path.");
  return queryPath;
}

function getControlRootFromQueryPath(queryPath, queryTitle = "Query") {
  const nodeRequire = getNodeRequire();
  const pathMod = nodeRequire("node:path");
  const normalized = String(queryPath || "").replace(/\\/g, "/");
  if (!normalized || !normalized.includes("/")) {
    throw new Error(`${queryTitle} has no parent query directory: ${queryPath}`);
  }
  const queryDirPath = pathMod.posix.dirname(normalized);
  const controlRoot = pathMod.posix.dirname(queryDirPath);
  if (!controlRoot || controlRoot === ".") {
    throw new Error(`Could not determine control root from query path: ${queryPath}`);
  }
  return controlRoot;
}

module.exports = {
  getNodeRequire,
  getVaultBasePath,
  getVaultName,
  getActiveQueryPath,
  getControlRootFromQueryPath,
};
