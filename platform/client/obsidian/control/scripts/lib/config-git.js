"use strict";

const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const CONFIG_REF = "refs/heads/autoscribe/config";
const CONFIG_SYNCED_REF = "refs/autoscribe/config-synced";
const GIT = process.env.AUTOSCRIBE_GIT || "git";

function gitEnv(extra = {}) {
  return {
    ...process.env,
    GIT_AUTHOR_NAME: process.env.GIT_AUTHOR_NAME || "AutoScribe Config",
    GIT_AUTHOR_EMAIL: process.env.GIT_AUTHOR_EMAIL || "autoscribe@localhost",
    GIT_COMMITTER_NAME: process.env.GIT_COMMITTER_NAME || "AutoScribe Config",
    GIT_COMMITTER_EMAIL: process.env.GIT_COMMITTER_EMAIL || "autoscribe@localhost",
    ...extra,
  };
}

function runGit(root, args, { input = null, env = {}, allowFailure = false } = {}) {
  const result = childProcess.spawnSync(GIT, args, {
    cwd: root,
    env: gitEnv(env),
    input,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0 && !allowFailure) {
    const detail = String(result.stderr || result.stdout || "git failed").trim();
    throw new Error(`git ${args.join(" ")} failed: ${detail}`);
  }
  return result;
}

function revision(root, ref) {
  const result = runGit(root, ["rev-parse", "--verify", ref], { allowFailure: true });
  return result.status === 0 ? String(result.stdout).trim() : null;
}

function safeIdentity(raw) {
  const value = String(raw || "").trim();
  if (!value || !/^[A-Za-z0-9._-]+$/.test(value)) {
    throw new Error(`Invalid AutoScribe config identity: ${value || "(blank)"}`);
  }
  return value;
}

function readJsonAt(root, ref, relativePath) {
  if (!revision(root, ref)) return null;
  const result = runGit(root, ["show", `${ref}:${relativePath}`], { allowFailure: true });
  if (result.status !== 0) return null;
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`Invalid JSON at ${ref}:${relativePath}: ${error.message || error}`);
  }
}

function listJsonAt(root, category, ref = CONFIG_REF) {
  if (!revision(root, ref)) return [];
  const listing = runGit(root, ["ls-tree", "-r", "--name-only", ref, "--", `${category}/`]);
  const records = [];
  for (const relativePath of String(listing.stdout).split(/\r?\n/).map((x) => x.trim()).filter(Boolean)) {
    if (!relativePath.endsWith(".json")) continue;
    const record = readJsonAt(root, ref, relativePath);
    if (record) records.push(record);
  }
  return records;
}

function payloadListing(root, ref) {
  if (!ref) return "";
  const result = runGit(root, ["ls-tree", "-r", ref, "--", "plans", "instructions"], { allowFailure: true });
  return result.status === 0 ? String(result.stdout) : "";
}

function configStatus(root) {
  const head = revision(root, CONFIG_REF);
  const synced = revision(root, CONFIG_SYNCED_REF);
  return { head, synced, current: payloadListing(root, head) === payloadListing(root, synced) };
}

function writeJson(root, category, identity, value, message) {
  const safeCategory = String(category || "");
  if (safeCategory !== "plans") {
    throw new Error(`Frontend may not write config category: ${safeCategory}`);
  }
  const safeId = safeIdentity(identity);
  const relativePath = `${safeCategory}/${safeId}.json`;
  const bytes = `${JSON.stringify(value, null, 2)}\n`;

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const old = revision(root, CONFIG_REF);
    const index = path.join(os.tmpdir(), `autoscribe-config-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.index`);
    try {
      const env = { GIT_INDEX_FILE: index };
      if (old) runGit(root, ["read-tree", old], { env });
      else runGit(root, ["read-tree", "--empty"], { env });

      const blob = String(runGit(root, ["hash-object", "-w", "--stdin"], { input: bytes }).stdout).trim();
      runGit(root, ["update-index", "--add", "--cacheinfo", "100644", blob, relativePath], { env });
      const tree = String(runGit(root, ["write-tree"], { env }).stdout).trim();

      if (old) {
        const oldTree = String(runGit(root, ["show", "-s", "--format=%T", old]).stdout).trim();
        if (tree === oldTree) return old;
      }

      const commitArgs = ["commit-tree", tree];
      if (old) commitArgs.push("-p", old);
      const commit = String(runGit(root, commitArgs, { input: `${message}\n` }).stdout).trim();
      const expected = old || "0000000000000000000000000000000000000000";
      const update = runGit(root, ["update-ref", "-m", "AutoScribe config ledger", CONFIG_REF, commit, expected], { allowFailure: true });
      if (update.status === 0) return commit;
    } finally {
      try { fs.unlinkSync(index); } catch {}
    }
  }
  throw new Error("AutoScribe config ref kept changing; save the plan again.");
}

function recordId(record) {
  return String(record?.record_identity || record?.slug || record?.identity || record?.key || "").trim();
}

function instructionForUi(record) {
  const extra = record?.extra && typeof record.extra === "object" ? record.extra : {};
  const slug = String(extra.slug || record?.slug || record?.identity || "").trim();
  if (!slug) return null;
  const prefix = slug.split(".")[0] || "";
  const inferred = prefix === "std" ? "standing" : prefix === "rol" ? "role" : prefix === "ctx" ? "context" : ["tsk", "ins", "spc"].includes(prefix) ? "task" : "";
  return {
    slug,
    record_identity: String(record?.identity || record?.record_identity || slug),
    title: String(extra.title || record?.title || slug),
    scope: String(extra.scope || extra.component || record?.scope || inferred),
    component: String(extra.component || record?.component || inferred),
    path: extra.source_path || record?.path || null,
    source: "autoscribe/config",
  };
}

function overlayById(base, additions, convert = (value) => value) {
  const map = new Map();
  for (const record of Array.isArray(base) ? base : []) {
    const key = recordId(record);
    if (key) map.set(key, record);
  }
  for (const raw of additions) {
    const record = convert(raw);
    if (!record) continue;
    const key = recordId(record);
    if (key) map.set(key, record);
  }
  return [...map.values()];
}

function readPlanManagerSnapshot(root) {
  const state = readJsonAt(root, CONFIG_REF, "state/control.json") || {};
  const source = state.catalogs && typeof state.catalogs === "object" ? state.catalogs : {};
  const catalogs = {
    instructions: Array.isArray(source.instructions) ? [...source.instructions] : [],
    plans: Array.isArray(source.plans) ? [...source.plans] : [],
    engines: Array.isArray(source.engines) ? [...source.engines] : [],
    models: Array.isArray(source.models) ? [...source.models] : [],
    scripts: Array.isArray(source.scripts) ? [...source.scripts] : [],
    rag_profiles: Array.isArray(source.rag_profiles) ? [...source.rag_profiles] : [],
  };
  catalogs.instructions = overlayById(catalogs.instructions, listJsonAt(root, "instructions"), instructionForUi);
  catalogs.plans = overlayById(catalogs.plans, listJsonAt(root, "plans"));
  return {
    catalogs,
    refreshed_at: state.refreshed_at || null,
    config: configStatus(root),
    state_available: Boolean(state.catalogs),
  };
}

function savePlan(root, record) {
  const identity = safeIdentity(recordId(record));
  return writeJson(root, "plans", identity, record, `AUTOSCRIBE CONFIG plan ${identity}`);
}

module.exports = {
  CONFIG_REF,
  CONFIG_SYNCED_REF,
  configStatus,
  listJsonAt,
  readJsonAt,
  readPlanManagerSnapshot,
  savePlan,
};
