"use strict";
const { serviceCall } = require("./dispatch-service.js");

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Obsidian vault path is unavailable");
  return root;
}

async function gitFiles(app, action, request = {}) {
  const input = { version: 1, action, ...request };
  const response = await serviceCall(app, "git-files", input);
  const output = JSON.parse(response.stdout.trim() || "{}");
  if (!output.ok) throw new Error(output.error || `Rust Git operation failed: ${action}`);
  return output;
}

module.exports = { gitFiles, vaultRoot };
