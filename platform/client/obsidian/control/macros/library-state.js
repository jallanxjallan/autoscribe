"use strict";

/**
 * QuickAdd launcher: Library State
 *
 * The active vault supplies the instructions; _control supplies the UI.
 */
module.exports = async function libraryState(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = require;
  const path = nodeRequire("node:path");

  const vaultRoot = path.resolve(app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath);
  const implementation = path.join(vaultRoot, "_control", "scripts", "ui", "library-state.js");

  const runLibraryState = nodeRequire(implementation);
  if (typeof runLibraryState !== "function") {
    throw new Error(`Library State implementation does not export a function: ${implementation}`);
  }
  return runLibraryState({ ...params, app });
};
