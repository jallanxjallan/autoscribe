"use strict";

const { buildManifest } = require("./operation-manifest");
const { getVaultBasePath } = require("./query-runtime");

const REGISTRY_KEY = Symbol.for("autoscribe.current-selection.by-vault");

function registry(app) {
  if (!app || typeof app !== "object") {
    throw new Error("Current selection requires the active Obsidian app.");
  }

  if (!app[REGISTRY_KEY]) {
    Object.defineProperty(app, REGISTRY_KEY, {
      value: new Map(),
      configurable: true,
      enumerable: false,
      writable: false,
    });
  }

  return app[REGISTRY_KEY];
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
