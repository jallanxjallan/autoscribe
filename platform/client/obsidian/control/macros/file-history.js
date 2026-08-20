"use strict";

const { openWorkflowModal } = require("../scripts/lib/workflow-modal.js");
const { renderFileHistory } = require("../scripts/ui/file-history.js");

module.exports = async function fileHistory(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) {
    throw new Error("Obsidian app object unavailable.");
  }

  return openWorkflowModal({
    app,
    title: "File History",
    render: (container) => renderFileHistory({ app, container }),
  });
};
