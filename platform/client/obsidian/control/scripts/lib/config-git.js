"use strict";

const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { loadConfig } = require("./config-loader");

const GIT = process.env.AUTOSCRIBE_GIT || "git";
const CONTROL_REF = "HEAD";

function workflow() { return loadConfig("workflow").plan_manager || {}; }
function configured(key, envKey, fallback) {
  const fromEnv = String(process.env[envKey] || "").trim();
  if (fromEnv) return fromEnv;
  return String(workflow()[key] || fallback).trim();
}
function controlRoot() {
  return path.resolve(configured("control_root", "AUTOSCRIBE_CONTROL_ROOT", "/home/jeremy/Work/Control"));
}
function controlBranch() { return configured("branch", "AUTOSCRIBE_CONTROL_BRANCH", "master"); }
function configRemote() { return configured("push_remote", "AUTOSCRIBE_CONFIG_REMOTE", "origin"); }
function ascCommand() {
  const command = configured("asc_command", "AUTOSCRIBE_ASC", "");
  if (command) return command;
  const local = "/home/jeremy/Python3.13Env/bin/asc";
  return fs.existsSync(local) ? local : "asc";
}

function gitEnv(extra = {}) {
  return {
    ...process.env,
    GIT_AUTHOR_NAME: process.env.GIT_AUTHOR_NAME || "AutoScribe Control",
    GIT_AUTHOR_EMAIL: process.env.GIT_AUTHOR_EMAIL || "autoscribe@localhost",
    GIT_COMMITTER_NAME: process.env.GIT_COMMITTER_NAME || "AutoScribe Control",
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
    const stdout = [], stderr = [];
    let settled = false;
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", (error) => {
      if (!settled) { settled = true; reject(error); }
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
        reject(new Error(`git ${args.join(" ")} failed: ${String(result.stderr || result.stdout || "git failed").trim()}`));
      } else {
        resolve(result);
      }
    });
    child.stdin.on("error", (error) => {
      if (error?.code !== "EPIPE" && !settled) {
        settled = true; child.kill(); reject(error);
      }
    });
    child.stdin.end(input == null ? undefined : input);
  });
}

async function ensureControlRepo() {
  const root = controlRoot();
  if (!fs.existsSync(root)) throw new Error(`AutoScribe Control repository not found: ${root}`);
  const top = await runGit(root, ["rev-parse", "--show-toplevel"], { allowFailure: true });
  if (top.status !== 0) throw new Error(`Not a Git worktree: ${root}`);
  const actual = path.resolve(String(top.stdout).trim());
  if (actual !== root) throw new Error(`Configured Control root resolves to ${actual}, expected ${root}`);
  const branch = String((await runGit(root, ["branch", "--show-current"])).stdout).trim();
  if (branch !== controlBranch()) throw new Error(`Control must be on ${controlBranch()}; currently ${branch || "(detached)"}`);
  return root;
}

function safeIdentity(raw) {
  const value = String(raw || "").trim();
  if (!value || !/^[A-Za-z0-9._-]+$/.test(value)) {
    throw new Error(`Invalid AutoScribe config identity: ${value || "(blank)"}`);
  }
  return value;
}

function recordId(record) {
  return String(record?.record_identity || record?.slug || record?.identity || record?.key || "").trim();
}
function inferComponent(slug) {
  const prefix = String(slug || "").split(".")[0];
  return prefix === "std" ? "standing"
    : prefix === "rul" ? "rule"
    : prefix === "rol" ? "role"
    : prefix === "ctx" ? "context"
    : ["tsk", "ins", "spc"].includes(prefix) ? "task"
    : "";
}
function parseScalar(raw) {
  const value = String(raw || "").trim();
  if (!value) return "";
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}
function splitFrontmatter(text) {
  const lines = String(text).replace(/\r\n/g, "\n").split("\n");
  if (lines[0]?.trim() !== "---") return null;
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (end < 0) return null;
  const fm = {};
  for (const line of lines.slice(1, end)) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (match) fm[match[1]] = parseScalar(match[2]);
  }
  return { fm, body: lines.slice(end + 1).join("\n").trim() };
}

async function committedInstructionRecords(root) {
  const listing = await runGit(root, ["ls-tree", "-r", "--name-only", CONTROL_REF, "--", "instructions/"], { allowFailure: true });
  if (listing.status !== 0) return [];
  const paths = String(listing.stdout).split(/\r?\n/)
    .map((value) => value.trim())
    .filter((value) => value.endsWith(".md"));

  const records = [];
  const seen = new Set();
  for (const relative of paths) {
    const shown = await runGit(root, ["show", `${CONTROL_REF}:${relative}`]);
    const parsed = splitFrontmatter(shown.stdout);
    if (!parsed) continue;
    const kind = String(parsed.fm.record || parsed.fm.type || parsed.fm.kind || "").toLowerCase();
    if (kind !== "instruction") continue;
    const slug = String(parsed.fm.slug || "").trim();
    if (!slug) continue;
    if (seen.has(slug)) throw new Error(`Duplicate committed instruction slug: ${slug}`);
    seen.add(slug);
    const component = String(parsed.fm.component || parsed.fm.class || inferComponent(slug)).trim();
    const title = String(parsed.fm.title || parsed.fm.label || path.basename(relative, path.extname(relative))).trim();
    const description = String(parsed.fm.description || parsed.fm.summary || "").trim();
    records.push({
      slug,
      record_identity: slug,
      title,
      label: title,
      description,
      scope: component,
      component,
      path: relative,
      source: "control",
    });
  }
  return records;
}

async function readJsonAt(root, ref, relativePath) {
  const result = await runGit(root, ["show", `${ref}:${relativePath}`], { allowFailure: true });
  if (result.status !== 0) return null;
  try { return JSON.parse(result.stdout); }
  catch (error) { throw new Error(`Invalid JSON at ${ref}:${relativePath}: ${error.message || error}`); }
}

async function committedPlans(root) {
  const listing = await runGit(root, ["ls-tree", "-r", "--name-only", CONTROL_REF, "--", "plans/"], { allowFailure: true });
  if (listing.status !== 0) return [];
  const paths = String(listing.stdout).split(/\r?\n/).map((x) => x.trim()).filter((x) => x.endsWith(".json"));
  const records = await Promise.all(paths.map((relative) => readJsonAt(root, CONTROL_REF, relative)));
  return records.filter(Boolean);
}

function registryRecords(value, defaultKeyField = "key") {
  if (Array.isArray(value)) return value.filter((item) => item && typeof item === "object");
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).map(([key, raw]) => {
    const record = raw && typeof raw === "object" && !Array.isArray(raw) ? { ...raw } : {};
    if (!record[defaultKeyField]) record[defaultKeyField] = key;
    return record;
  });
}
function snapshotRegistries(snapshot) {
  const direct = snapshot?.registries && typeof snapshot.registries === "object" ? snapshot.registries : {};
  const catalogs = snapshot?.catalogs && typeof snapshot.catalogs === "object" ? snapshot.catalogs : {};
  return { ...catalogs, ...direct };
}

async function runComponentsSnapshot(root) {
  const command = ascCommand();
  const maxBuffer = Number(loadConfig("workflow")?.control_loader?.asc_snapshot_max_buffer_bytes || 10 * 1024 * 1024);
  return new Promise((resolve, reject) => {
    childProcess.execFile(command, ["components", "snapshot"], {
      cwd: root,
      env: process.env,
      maxBuffer,
    }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(`asc components snapshot failed: ${String(stderr || error.message || error).trim()}`));
        return;
      }
      try {
        const parsed = JSON.parse(String(stdout || "{}"));
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("snapshot is not a JSON object");
        resolve(parsed);
      } catch (parseError) {
        reject(new Error(`asc components snapshot returned invalid JSON: ${parseError.message || parseError}`));
      }
    });
  });
}

async function readPlanManagerSnapshot(_vaultRoot) {
  const root = await ensureControlRepo();
  const [instructions, plans, snapshot] = await Promise.all([
    committedInstructionRecords(root),
    committedPlans(root),
    runComponentsSnapshot(root),
  ]);
  const registries = snapshotRegistries(snapshot);
  const engines = registryRecords(registries.engines);
  const models = registryRecords(registries.models);
  const scripts = registryRecords(registries.local_scripts || registries.scripts);
  const ragProfiles = registryRecords(registries.rag_profiles);

  const remoteHead = await runGit(root, ["rev-parse", "--verify", `${configRemote()}/${controlBranch()}`], { allowFailure: true });
  const localHead = String((await runGit(root, ["rev-parse", "HEAD"])).stdout).trim();

  return {
    catalogs: { instructions, plans, engines, models, scripts, rag_profiles: ragProfiles },
    catalog: {
      source: "committed Control repository",
      available: true,
      control_root: root,
      control_branch: controlBranch(),
      committed_instructions: instructions.length,
      plans: plans.length,
      unpublished: remoteHead.status !== 0 || String(remoteHead.stdout).trim() !== localHead,
      engines: engines.length,
      models: models.length,
      scripts: scripts.length,
      rag_profiles: ragProfiles.length,
    },
  };
}

async function requireCleanBeforePlanWrite(root) {
  const status = await runGit(root, ["status", "--porcelain", "--untracked-files=all"]);
  const dirty = String(status.stdout).trim();
  if (dirty) {
    throw new Error(
      "Control has uncommitted changes. Commit or discard instruction/component edits before saving a plan."
    );
  }
}

async function commitPlanFile(root, record, { deletePlan = false } = {}) {
  const identity = safeIdentity(recordId(record));
  await requireCleanBeforePlanWrite(root);
  const relative = `plans/${identity}.json`;
  const absolute = path.join(root, relative);
  fs.mkdirSync(path.dirname(absolute), { recursive: true });

  if (deletePlan) {
    if (!fs.existsSync(absolute)) {
      const existing = await readJsonAt(root, CONTROL_REF, relative);
      if (!existing) throw new Error(`Plan not found in Control/master: ${identity}`);
    }
    try { fs.unlinkSync(absolute); } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await runGit(root, ["add", "-A", "--", relative]);
  } else {
    fs.writeFileSync(absolute, `${JSON.stringify(record, null, 2)}\n`, "utf8");
    await runGit(root, ["add", "--", relative]);
  }

  const staged = await runGit(root, ["diff", "--cached", "--quiet"], { allowFailure: true });
  if (staged.status !== 0) {
    const verb = deletePlan ? "Delete" : "Update";
    await runGit(root, ["commit", "-m", `${verb} plan ${identity}`]);
  }

  const commit = String((await runGit(root, ["rev-parse", "HEAD"])).stdout).trim();
  await runGit(root, ["push", configRemote(), `${controlBranch()}:${controlBranch()}`]);
  return commit;
}

async function savePlan(_vaultRoot, record) {
  const root = await ensureControlRepo();
  return commitPlanFile(root, record);
}

async function deletePlan(_vaultRoot, identity) {
  const root = await ensureControlRepo();
  const safeId = safeIdentity(identity);
  const existing = await readJsonAt(root, CONTROL_REF, `plans/${safeId}.json`);
  if (!existing) throw new Error(`Plan not found in Control/master: ${safeId}`);
  return commitPlanFile(root, existing, { deletePlan: true });
}

module.exports = {
  CONTROL_REF,
  controlRoot,
  readJsonAt,
  readPlanManagerSnapshot,
  savePlan,
  deletePlan,
  committedInstructionRecords,
  runComponentsSnapshot,
};
