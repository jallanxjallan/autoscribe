"use strict";

/**
 * Compatibility launcher. Instructions are ordinary Markdown records now, so
 * creation is delegated to the generic Create Note macro and its templates.
 */
module.exports = async function createInstruction(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const root = path.resolve(app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath);
  const implementation = path.join(root, "_control", "macros", "create-note.js");

  try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}
  const run = nodeRequire(implementation);
  if (typeof run !== "function") throw new Error(`Create Note implementation missing: ${implementation}`);
  return run({ ...params, app });
};
