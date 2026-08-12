"use strict";

/**
 * QuickAdd launcher: Create Instruction
 * The active vault receives the instruction; _control supplies the UI.
 */
module.exports = async function createInstruction(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const vaultRoot = path.resolve(app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath);
  const implementation = path.join(vaultRoot, "_control", "scripts", "ui", "create-instruction.js");

  try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}
  const run = nodeRequire(implementation);
  if (typeof run !== "function") throw new Error(`Create Instruction implementation missing: ${implementation}`);
  return run({ ...params, app });
};
