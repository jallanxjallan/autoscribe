// Open _control/Dashboard.md in the main workspace.

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

module.exports = async ({ app }) => {
  const loader = createControlRuntime(app);
  const { loadConfig } = loader.requireControl("scripts/lib/config-loader.js");
  const candidates = loadConfig("paths").dashboard_candidates || [];

  const file = candidates
    .map((path) => app.vault.getAbstractFileByPath(path))
    .find((candidate) => candidate?.extension === "md");

  if (!file) {
    console.warn("Dashboard not found.");
    return;
  }

  const { openFileInMain } = loader.requireControl("scripts/lib/workspace.js");
  await openFileInMain(app, file, { mode: "preview" });
};
