// Open _control/Dashboard.md in the main workspace.

const path = require("node:path");

module.exports = async ({ app }) => {
  const candidates = [
    "_control/Dashboard.md",
    "Dashboard.md",
  ];

  const file = candidates
    .map((path) => app.vault.getAbstractFileByPath(path))
    .find((candidate) => candidate?.extension === "md");

  if (!file) {
    console.warn("Dashboard not found.");
    return;
  }

  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const { openFileInMain } = require(path.join(root, "_control", "scripts", "lib", "workspace.js"));
  await openFileInMain(app, file, { mode: "preview" });
};
