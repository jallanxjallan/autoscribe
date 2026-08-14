"use strict";
const { run, serviceCommand } = require("./dispatch-service.js");

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Obsidian vault path is unavailable");
  return root;
}

async function gitFiles(app, action, request = {}) {
  const root = vaultRoot(app);
  const executable = serviceCommand(app);
  const input = { version: 1, repository_path: root, action, ...request };
  const response = await run(executable.command, [...executable.prefix, "git-files"], {
    cwd: root,
    input: JSON.stringify(input),
  });
  const output = JSON.parse(response.stdout.trim() || "{}");
  if (!output.ok) throw new Error(output.error || `Rust Git operation failed: ${action}`);
  return output;
}

module.exports = { gitFiles, vaultRoot };
