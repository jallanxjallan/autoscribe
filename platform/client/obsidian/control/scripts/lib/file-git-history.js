"use strict";
const { gitFiles } = require("./git-service.js");

async function liveState(app, vaultPath) {
  const output = await gitFiles(app, "inspect", { paths: [vaultPath] });
  const row = output.items?.[0] || {};
  return {
    path: vaultPath,
    repo_path: vaultPath,
    status: row.git_status || row.repo_state || "clean",
    dirty: Boolean(row.git_status),
    latest_commit: row.latest_commit || null,
  };
}
async function history(app, vaultPath) {
  return (await gitFiles(app, "history", { path: vaultPath })).items || [];
}
async function listFileStashes(app, vaultPath = null) {
  const request = vaultPath ? { path: vaultPath } : {};
  return (await gitFiles(app, "stash-list", request)).items || [];
}
async function stashCurrent(app, vaultPath) {
  return (await gitFiles(app, "stash-create", { path: vaultPath })).item;
}
async function restoreFileStash(app, vaultPath, id) {
  return (await gitFiles(app, "stash-restore", { path: vaultPath, id })).item;
}
async function dropFileStash(app, vaultPath, id) {
  return (await gitFiles(app, "stash-drop", { path: vaultPath, id })).item;
}
async function restoreVersion(app, vaultPath, revision) {
  return gitFiles(app, "restore-version", { path: vaultPath, revision });
}

module.exports = { liveState, history, restoreVersion, listFileStashes, stashCurrent, restoreFileStash, dropFileStash };
