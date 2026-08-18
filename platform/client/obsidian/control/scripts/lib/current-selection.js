"use strict";

const { buildManifest } = require("./operation-manifest");
const { getVaultBasePath } = require("./query-runtime");
const { loadConfig } = require("./config-loader");
function registryKey() { return Symbol.for(String(loadConfig("protocol").session_keys?.current_selection_registry || "autoscribe.current-selection.by-vault")); }

function registry(app) {
  if (!app || typeof app !== "object") {
    throw new Error("Current selection requires the active Obsidian app.");
  }

  if (!app[registryKey()]) {
    Object.defineProperty(app, registryKey(), {
      value: new Map(),
      configurable: true,
      enumerable: false,
      writable: false,
    });
  }

  return app[registryKey()];
}

function vaultKey(app) {
  const root = getVaultBasePath(app);
  if (!root) throw new Error("Current selection requires an active filesystem-backed vault.");
  return root;
}

function setCurrentSelection({ app, queryName, namespace, options = {}, items = [], extra = {} }) {
  if (!Array.isArray(items)) throw new Error("Current selection items must be an array.");

  const manifest = buildManifest({
    app,
    operation: "current-selection",
    queryName,
    namespace,
    options,
    items,
    extra,
  });

  registry(app).set(vaultKey(app), manifest);
  return manifest;
}

function getCurrentSelection(app) {
  return registry(app).get(vaultKey(app)) || null;
}

function clearCurrentSelection(app) {
  return registry(app).delete(vaultKey(app));
}

module.exports = {
  setCurrentSelection,
  getCurrentSelection,
  clearCurrentSelection,
};
