"use strict";

const { openWorkflowModal } = require("../scripts/lib/workflow-modal.js");
const { renderFileState } = require("../scripts/ui/file-state.js");

module.exports = async function fileState(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) {
    throw new Error("Obsidian app object unavailable.");
  }

  return openWorkflowModal({
    app,
    title: "File State",
    render: (container) => renderFileState({ app, container }),
  });
};
