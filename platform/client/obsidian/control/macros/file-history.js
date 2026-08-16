"use strict";

module.exports = async function fileHistory(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) {
    throw new Error("Obsidian app object unavailable.");
  }

  const nodeRequire = require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relativePath) => nodeRequire(
    path.join(base, "_control", ...relativePath.split("/"))
  );
  const { openWorkflowModal } = load("scripts/lib/workflow-modal.js");
  const { renderFileHistory } = load("scripts/ui/file-history.js");

  return openWorkflowModal({
    app,
    title: "File History",
    render: (container) => renderFileHistory({ app, container }),
  });
};
