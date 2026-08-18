// Open _control/Dashboard.md in the main workspace.

const path = require("node:path");

module.exports = async ({ app }) => {
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const { loadConfig } = require(path.join(root, "_control", "scripts", "lib", "config-loader.js"));
  const candidates = loadConfig("paths").dashboard_candidates || [];

  const file = candidates
    .map((path) => app.vault.getAbstractFileByPath(path))
    .find((candidate) => candidate?.extension === "md");

  if (!file) {
    console.warn("Dashboard not found.");
    return;
  }

  const { openFileInMain } = require(path.join(root, "_control", "scripts", "lib", "workspace.js"));
  await openFileInMain(app, file, { mode: "preview" });
};
