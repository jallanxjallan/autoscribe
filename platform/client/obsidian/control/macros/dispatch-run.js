"use strict";

module.exports = async function dispatch_run(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relativePath) => nodeRequire(path.join(base, "_control", ...relativePath.split("/")));
  const { openWorkflowModal } = load("scripts/lib/workflow-modal.js");
  const { renderDispatchRun } = load("scripts/ui/dispatch-run.js");
  return openWorkflowModal({ app, title: "Dispatch Run", render: (container) => renderDispatchRun({ app, container }) });
};
