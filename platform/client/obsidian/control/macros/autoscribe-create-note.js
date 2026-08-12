"use strict";

module.exports = async function create_note(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const implementation = path.join(base, "_control", "macros", "create_typed_note.js");

  try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}
  const run = nodeRequire(implementation);
  if (typeof run !== "function") throw new Error(`Create Note implementation missing: ${implementation}`);
  return run({ ...params, app });
};
