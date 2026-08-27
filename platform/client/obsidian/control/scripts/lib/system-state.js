"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Could not determine vault root.");
  return path.resolve(root);
}

function git(root, args, { allowFailure = false } = {}) {
  const result = spawnSync("/usr/bin/git", ["-C", root, ...args], { encoding: "utf8" });
  if (result.status !== 0 && !allowFailure) {
    throw new Error((result.stderr || result.stdout || `git exited ${result.status}`).trim());
  }
  return result;
}

function gitSummary(root) {
  const branch = git(root, ["branch", "--show-current"]).stdout.trim() || "detached HEAD";
  const porcelain = git(root, ["status", "--porcelain=v1"]).stdout;
  let staged = 0, modified = 0, untracked = 0, conflicted = 0;
  for (const line of porcelain.split(/\r?\n/).filter(Boolean)) {
    const code = line.slice(0, 2);
    if (code === "??") { untracked += 1; continue; }
    if (code[0] && code[0] !== " ") staged += 1;
    if (code[1] && code[1] !== " ") modified += 1;
    if (["DD", "AU", "UD", "UA", "DU", "AA", "UU"].includes(code)) conflicted += 1;
  }
  const latest = git(root, ["log", "-1", "--format=%h%x09%cr%x09%s"], { allowFailure: true }).stdout.trim();
  const upstream = git(root, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], { allowFailure: true });
  let ahead = null, behind = null;
  if (upstream.status === 0) {
    const values = upstream.stdout.trim().split(/\s+/).map(Number);
    behind = Number.isFinite(values[0]) ? values[0] : null;
    ahead = Number.isFinite(values[1]) ? values[1] : null;
  }
  return { root, branch, latest, ahead, behind, staged, modified, untracked, conflicted };
}

async function readSystemState(app) {
  const root = vaultRoot(app);
  const state = { refreshed_at: new Date().toISOString(), git: null, pipeline: null, errors: {} };
  try { state.git = gitSummary(root); } catch (error) { state.errors.git = error?.message || String(error); }
  try {
    const statePath = path.join(root, ".autoscribe", "control-state.json");
    if (!fs.existsSync(statePath)) throw new Error("No svc refresh snapshot yet. Run 'svc refresh' from the vault root.");
    const saved = JSON.parse(fs.readFileSync(statePath, "utf8"));
    const pipeline = saved.pipeline || {};
    state.pipeline = {
      counts: {
        total: Number(pipeline.active_dispatches || 0),
        unclaimed: Number(pipeline.pending_uploads || 0),
        waiting: Number(pipeline.active_dispatches || 0),
        response_pending: Number(pipeline.pending_responses || 0),
        uncertain: Number(pipeline.uncertain_uploads || 0),
        reviewed: 0,
      },
      handoffs: Array.isArray(saved.dispatches) ? saved.dispatches.filter((row) => row.status === "dispatched") : [],
    };
    state.refreshed_at = saved.refreshed_at || state.refreshed_at;
  } catch (error) {
    state.errors.pipeline = error?.message || String(error);
  }
  return state;
}

module.exports = { readSystemState };
