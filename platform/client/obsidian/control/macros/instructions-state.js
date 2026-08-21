"use strict";

/**
 * QuickAdd launcher: Instructions State
 *
 * The active vault supplies the instructions; _control supplies the UI.
 */
module.exports = async function instructionsState(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");

  const vaultRoot = path.resolve(app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath);
  const implementation = path.join(vaultRoot, "_control", "scripts", "instructions-state.js");

  // Avoid stale code if Instructions State is edited during an Obsidian session.
  try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}

  const runInstructionsState = nodeRequire(implementation);
  if (typeof runInstructionsState !== "function") {
    throw new Error(`Instructions State implementation does not export a function: ${implementation}`);
  }
  return runInstructionsState({ ...params, app });
};
