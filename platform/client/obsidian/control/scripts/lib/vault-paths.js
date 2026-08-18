"use strict";

const path = require("node:path");
const { loadConfig } = require("./config-loader");

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;

  if (typeof adapter?.getBasePath === "function") {
    return adapter.getBasePath();
  }

  if (adapter?.basePath) {
    return adapter.basePath;
  }

  return "";
}

function getVaultAbsolutePath(app, vaultPath) {
  const base = getVaultBasePath(app);
  if (!base || !vaultPath) return null;

  return path.join(base, String(vaultPath).replace(/^\/+/, ""));
}

function getAutoscribeDir(app) {
  const base = getVaultBasePath(app);
  if (!base) {
    throw new Error("Could not resolve active vault root for .autoscribe directory.");
  }
  return path.join(base, String(loadConfig("paths").runtime_dir || ".autoscribe"));
}

function getSelectionsDir(app) {
  return path.join(getAutoscribeDir(app), String(loadConfig("paths").selection_dir || "selections"));
}

function getWorkflowDir(app, kind = "") {
  const dir = path.join(getAutoscribeDir(app), String(loadConfig("paths").workflow_dir || "workflow"));
  return kind ? path.join(dir, String(kind).replace(/^\/+|\/+$/g, "")) : dir;
}

module.exports = {
  getVaultBasePath,
  getVaultAbsolutePath,
  getAutoscribeDir,
  getSelectionsDir,
  getWorkflowDir,
};
