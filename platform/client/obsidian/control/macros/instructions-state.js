"use strict";

function createControlRuntime(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const loaderPath = path.join(base, "_control", "scripts", "lib", "control-loader.js");
  try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
  const { createControlLoader } = nodeRequire(loaderPath);
  return createControlLoader({ app, controlRoot: "_control" });
}

/**
 * QuickAdd launcher: Instructions State
 *
 * The active vault supplies the instructions; _control supplies the UI.
 */
module.exports = async function instructionsState(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault) throw new Error("Obsidian app object unavailable.");

  const loader = createControlRuntime(app);
  const runInstructionsState = loader.requireControl("scripts/instructions-state.js");
  if (typeof runInstructionsState !== "function") {
    throw new Error("Instructions State implementation does not export a function.");
  }
  return runInstructionsState({ ...params, app });
};
