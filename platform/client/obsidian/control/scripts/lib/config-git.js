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
  return new Promise((resolve, reject) => {
    const child = childProcess.spawn(GIT, args, {
      cwd: root,
      env: gitEnv(env),
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    let settled = false;

    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      reject(error);
    });
    child.on("close", (status) => {
      if (settled) return;
      settled = true;
      const result = {
        status,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      };
      if (status !== 0 && !allowFailure) {
        const detail = String(result.stderr || result.stdout || "git failed").trim();
        reject(new Error(`git ${args.join(" ")} failed: ${detail}`));
        return;
      }
      resolve(result);
    });

    child.stdin.on("error", (error) => {
      if (error?.code !== "EPIPE" && !settled) {
        settled = true;
        child.kill();
        reject(error);
      }
    });
    child.stdin.end(input == null ? undefined : input);
  });
}

async function revision(root, ref) {
  const result = await runGit(root, ["rev-parse", "--verify", ref], { allowFailure: true });
  return result.status === 0 ? String(result.stdout).trim() : null;
}

function safeIdentity(raw) {
  const value = String(raw || "").trim();
  if (!value || !/^[A-Za-z0-9._-]+$/.test(value)) {
    throw new Error(`Invalid AutoScribe config identity: ${value || "(blank)"}`);
  }
  return value;
}

async function readJsonAt(root, ref, relativePath) {
  if (!(await revision(root, ref))) return null;
  const result = await runGit(root, ["show", `${ref}:${relativePath}`], { allowFailure: true });
  if (result.status !== 0) return null;
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`Invalid JSON at ${ref}:${relativePath}: ${error.message || error}`);
  }
}

async function listJsonAt(root, category, ref = CONFIG_REF) {
  if (!(await revision(root, ref))) return [];
  const listing = await runGit(root, ["ls-tree", "-r", "--name-only", ref, "--", `${category}/`]);
  const paths = String(listing.stdout).split(/\r?\n/).map((x) => x.trim()).filter((x) => x.endsWith(".json"));
  const records = await Promise.all(paths.map((relativePath) => readJsonAt(root, ref, relativePath)));
  return records.filter(Boolean);
}

async function payloadListing(root, ref) {
  if (!ref) return "";
  const result = await runGit(root, ["ls-tree", "-r", ref, "--", "plans", "instructions"], { allowFailure: true });
  return result.status === 0 ? String(result.stdout) : "";
}

async function configStatus(root) {
  const [head, synced] = await Promise.all([
    revision(root, CONFIG_REF),
    revision(root, CONFIG_SYNCED_REF),
  ]);
  const [currentPayload, syncedPayload] = await Promise.all([
    payloadListing(root, head),
    payloadListing(root, synced),
  ]);
  return { head, synced, current: currentPayload === syncedPayload };
}

async function writeJson(root, category, identity, value, message) {
  const safeCategory = String(category || "");
  if (safeCategory !== "plans") {
    throw new Error(`Frontend may not write config category: ${safeCategory}`);
  }
  const safeId = safeIdentity(identity);
  const relativePath = `${safeCategory}/${safeId}.json`;
  const bytes = `${JSON.stringify(value, null, 2)}\n`;

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const old = await revision(root, CONFIG_REF);
    const index = path.join(os.tmpdir(), `autoscribe-config-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.index`);
    try {
      const env = { GIT_INDEX_FILE: index };
      if (old) await runGit(root, ["read-tree", old], { env });
      else await runGit(root, ["read-tree", "--empty"], { env });

      const blob = String((await runGit(root, ["hash-object", "-w", "--stdin"], { input: bytes })).stdout).trim();
      await runGit(root, ["update-index", "--add", "--cacheinfo", "100644", blob, relativePath], { env });
      const tree = String((await runGit(root, ["write-tree"], { env })).stdout).trim();

      if (old) {
        const oldTree = String((await runGit(root, ["show", "-s", "--format=%T", old])).stdout).trim();
        if (tree === oldTree) return old;
      }

      const commitArgs = ["commit-tree", tree];
      if (old) commitArgs.push("-p", old);
      const commit = String((await runGit(root, commitArgs, { input: `${message}\n` })).stdout).trim();
      const expected = old || "0000000000000000000000000000000000000000";
      const update = await runGit(root, ["update-ref", "-m", "AutoScribe config ledger", CONFIG_REF, commit, expected], { allowFailure: true });
      if (update.status === 0) return commit;
    } finally {
      try { await fs.promises.unlink(index); } catch {}
    }
  }
  throw new Error("AutoScribe config ref kept changing; save the plan again.");
}

async function deleteJson(root, category, identity, message) {
  const safeCategory = String(category || "");
  if (safeCategory !== "plans") {
    throw new Error(`Frontend may not delete config category: ${safeCategory}`);
  }
  const safeId = safeIdentity(identity);
  const relativePath = `${safeCategory}/${safeId}.json`;

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const old = await revision(root, CONFIG_REF);
    if (!old) throw new Error("AutoScribe config ref does not exist.");
    const existing = await runGit(root, ["cat-file", "-e", `${old}:${relativePath}`], { allowFailure: true });
    if (existing.status !== 0) return old;

    const index = path.join(os.tmpdir(), `autoscribe-config-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.index`);
    try {
      const env = { GIT_INDEX_FILE: index };
      await runGit(root, ["read-tree", old], { env });
      await runGit(root, ["update-index", "--force-remove", relativePath], { env });
      const tree = String((await runGit(root, ["write-tree"], { env })).stdout).trim();
      const commit = String((await runGit(root, ["commit-tree", tree, "-p", old], { input: `${message}\n` })).stdout).trim();
      const update = await runGit(root, ["update-ref", "-m", "AutoScribe config ledger", CONFIG_REF, commit, old], { allowFailure: true });
      if (update.status === 0) return commit;
    } finally {
      try { await fs.promises.unlink(index); } catch {}
    }
  }
  throw new Error("AutoScribe config ref kept changing; delete the plan again.");
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

async function readPlanManagerSnapshot(root) {
  const [stateValue, instructionRecords, planRecords, status] = await Promise.all([
    readJsonAt(root, CONFIG_REF, "state/control.json"),
    listJsonAt(root, "instructions"),
    listJsonAt(root, "plans"),
    configStatus(root),
  ]);
  const state = stateValue || {};
  const source = state.catalogs && typeof state.catalogs === "object" ? state.catalogs : {};
  const catalogs = {
    instructions: Array.isArray(source.instructions) ? [...source.instructions] : [],
    plans: Array.isArray(source.plans) ? [...source.plans] : [],
    engines: Array.isArray(source.engines) ? [...source.engines] : [],
    models: Array.isArray(source.models) ? [...source.models] : [],
    scripts: Array.isArray(source.scripts) ? [...source.scripts] : [],
    rag_profiles: Array.isArray(source.rag_profiles) ? [...source.rag_profiles] : [],
  };
  catalogs.instructions = overlayById(catalogs.instructions, instructionRecords, instructionForUi);
  catalogs.plans = overlayById(catalogs.plans, planRecords);
  return {
    catalogs,
    refreshed_at: state.refreshed_at || null,
    config: status,
    state_available: Boolean(state.catalogs),
  };
}

async function savePlan(root, record) {
  const identity = safeIdentity(recordId(record));
  return writeJson(root, "plans", identity, record, `AUTOSCRIBE CONFIG plan ${identity}`);
}

async function deletePlan(root, identity) {
  const safeId = safeIdentity(identity);
  return deleteJson(root, "plans", safeId, `AUTOSCRIBE CONFIG delete plan ${safeId}`);
}

module.exports = {
  CONFIG_REF,
  CONFIG_SYNCED_REF,
  configStatus,
  listJsonAt,
  readJsonAt,
  readPlanManagerSnapshot,
  savePlan,
  deletePlan,
};
