"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { runCommandSync } = require("./shell.js");
const { repositoryRoot, listTransportRuns } = require("./git-transport.js");
const { autoscribeVaultDir, safeReadJson, statInfo } = require("./vault-state.js");
const { loadRegistrySnapshot, loadControlSnapshot } = require("./feeder-control-loader.js");

function git(root, args, allowFailure = false) {
  return runCommandSync("git", ["-C", root, ...args], {
    cwd: root,
    allowFailure,
    maxBuffer: 8 * 1024 * 1024,
  });
}

function countGitChanges(porcelain) {
  const state = { staged: 0, modified: 0, untracked: 0, conflicted: 0 };
  for (const row of String(porcelain || "").split(/\r?\n/).filter(Boolean)) {
    const code = row.slice(0, 2);
    if (code === "??") state.untracked += 1;
    else {
      if (/^[MADRCU]/.test(code)) state.staged += 1;
      if (/^.[MADRCU]/.test(code)) state.modified += 1;
      if (/^(DD|AU|UD|UA|DU|AA|UU)$/.test(code)) state.conflicted += 1;
    }
  }
  return state;
}

function readGitState(app) {
  const root = repositoryRoot(app);
  const branch = String(git(root, ["branch", "--show-current"]).stdout || "").trim() || "detached HEAD";
  const porcelain = String(git(root, ["status", "--porcelain=v1"]).stdout || "");
  const latest = String(git(root, ["log", "-1", "--format=%h%x09%cr%x09%s"], true).stdout || "").trim();
  const upstream = git(root, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], true);
  const [behind = null, ahead = null] = upstream.status === 0
    ? String(upstream.stdout || "").trim().split(/\s+/).map(Number)
    : [];
  return { root, branch, latest, ahead, behind, ...countGitChanges(porcelain) };
}

function summarizeRuns(runs) {
  const counts = { total: runs.length, unclaimed: 0, waiting: 0, response_pending: 0, reviewed: 0 };
  for (const run of runs) counts[run.status] = (counts[run.status] || 0) + 1;
  return counts;
}

function recentHandoffs(app, limit = 10) {
  const dir = path.join(autoscribeVaultDir(app), "system-status");
  let names = [];
  try { names = fs.readdirSync(dir); } catch { return []; }
  return names.filter((name) => name.endsWith(".request.json")).sort().reverse().slice(0, limit).map((name) => {
    const stem = name.replace(/\.request\.json$/, "");
    const requestPath = path.join(dir, name);
    const stdoutPath = path.join(dir, `${stem}.stdout.log`);
    const stderrPath = path.join(dir, `${stem}.stderr.log`);
    return {
      stem,
      request: safeReadJson(requestPath, {}),
      request_file: statInfo(requestPath),
      stdout_file: statInfo(stdoutPath),
      stderr_file: statInfo(stderrPath),
      stdout: fs.existsSync(stdoutPath) ? fs.readFileSync(stdoutPath, "utf8").trim() : "",
      stderr: fs.existsSync(stderrPath) ? fs.readFileSync(stderrPath, "utf8").trim() : "",
    };
  });
}

function readPipelineState(app) {
  const runs = listTransportRuns(app);
  const registry = loadRegistrySnapshot(app);
  const control = loadControlSnapshot(app);
  return {
    runs,
    counts: summarizeRuns(runs),
    registry: registry.data,
    control: control.data,
    feeder_error: registry.error || control.error || null,
    handoffs: recentHandoffs(app),
  };
}

function readSystemState(app) {
  const state = { refreshed_at: new Date().toISOString(), git: null, pipeline: null, errors: {} };
  try { state.git = readGitState(app); } catch (error) { state.errors.git = error?.message || String(error); }
  try { state.pipeline = readPipelineState(app); } catch (error) { state.errors.pipeline = error?.message || String(error); }
  return state;
}

module.exports = { countGitChanges, readGitState, recentHandoffs, readPipelineState, readSystemState };
