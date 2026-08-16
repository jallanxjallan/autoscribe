"use strict";

module.exports = async function stage_files(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relativePath) => nodeRequire(path.join(base, "_control", ...relativePath.split("/")));
  const { openWorkflowModal } = load("scripts/lib/workflow-modal.js");
  const { renderStageFiles } = load("scripts/ui/stage-files.js");
  return openWorkflowModal({ app, title: "Stage Files", render: (container) => renderStageFiles({ app, container }) });
};
