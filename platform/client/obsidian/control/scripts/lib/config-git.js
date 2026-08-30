"use strict";

const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { loadConfig } = require("./config-loader");

const CONFIG_REF = "refs/heads/autoscribe/config";
const GIT = process.env.AUTOSCRIBE_GIT || "git";

function workflow() { return loadConfig("workflow").plan_manager || {}; }
function configured(remoteKey, envKey, fallback) {
  const fromEnv = String(process.env[envKey] || "").trim();
  if (fromEnv) return fromEnv;
  const value = workflow()[remoteKey];
  return String(value || fallback).trim();
}
function configRemote() { return configured("push_remote", "AUTOSCRIBE_CONFIG_REMOTE", "origin"); }
function ascCommand() {
  const configuredCommand = configured("asc_command", "AUTOSCRIBE_ASC", "");
  if (configuredCommand) return configuredCommand;
  const local = "/home/jeremy/Python3.13Env/bin/asc";
  return fs.existsSync(local) ? local : "asc";
}

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
    const child = childProcess.spawn(GIT, args, { cwd: root, env: gitEnv(env), stdio: ["pipe", "pipe", "pipe"] });
    const stdout = [], stderr = [];
    let settled = false;
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", (error) => { if (!settled) { settled = true; reject(error); } });
    child.on("close", (status) => {
      if (settled) return;
      settled = true;
      const result = { status, stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8") };
      if (status !== 0 && !allowFailure) {
        reject(new Error(`git ${args.join(" ")} failed: ${String(result.stderr || result.stdout || "git failed").trim()}`));
      } else resolve(result);
    });
    child.stdin.on("error", (error) => { if (error?.code !== "EPIPE" && !settled) { settled = true; child.kill(); reject(error); } });
    child.stdin.end(input == null ? undefined : input);
  });
}

async function revision(root, ref) {
  const result = await runGit(root, ["rev-parse", "--verify", ref], { allowFailure: true });
  return result.status === 0 ? String(result.stdout).trim() : null;
}

function safeIdentity(raw) {
  const value = String(raw || "").trim();
  if (!value || !/^[A-Za-z0-9._-]+$/.test(value)) throw new Error(`Invalid AutoScribe config identity: ${value || "(blank)"}`);
  return value;
}

async function readJsonAt(root, ref, relativePath) {
  if (!(await revision(root, ref))) return null;
  const result = await runGit(root, ["show", `${ref}:${relativePath}`], { allowFailure: true });
  if (result.status !== 0) return null;
  try { return JSON.parse(result.stdout); }
  catch (error) { throw new Error(`Invalid JSON at ${ref}:${relativePath}: ${error.message || error}`); }
}

async function listJsonAt(root, category, ref = CONFIG_REF) {
  if (!(await revision(root, ref))) return [];
  const listing = await runGit(root, ["ls-tree", "-r", "--name-only", ref, "--", `${category}/`], { allowFailure: true });
  if (listing.status !== 0) return [];
  const paths = String(listing.stdout).split(/\r?\n/).map((x) => x.trim()).filter((x) => x.endsWith(".json"));
  const records = await Promise.all(paths.map((relativePath) => readJsonAt(root, ref, relativePath)));
  return records.filter(Boolean);
}

function recordId(record) { return String(record?.record_identity || record?.slug || record?.identity || record?.key || "").trim(); }
function inferComponent(slug) {
  const prefix = String(slug || "").split(".")[0];
  return prefix === "std" ? "standing" : prefix === "rul" ? "rule" : prefix === "rol" ? "role" : prefix === "ctx" ? "context" : ["tsk", "ins", "spc"].includes(prefix) ? "task" : "";
}
function uiInstruction(record, source = "server") {
  const extra = record?.extra && typeof record.extra === "object" ? record.extra : {};
  const slug = String(record?.slug || record?.record_identity || record?.identity || extra.slug || "").trim();
  if (!slug) return null;
  const component = String(record?.component || record?.scope || extra.component || extra.scope || inferComponent(slug)).trim();
  return {
    slug,
    record_identity: slug,
    title: String(record?.title || record?.label || extra.title || slug),
    label: String(record?.label || record?.title || extra.title || slug),
    description: String(record?.description || extra.description || ""),
    scope: component,
    component,
    path: record?.path || extra.source_path || null,
    source,
  };
}
function overlayById(base, additions, convert = (x) => x) {
  const map = new Map();
  for (const raw of Array.isArray(base) ? base : []) { const record = convert(raw); const key = recordId(record); if (key) map.set(key, record); }
  for (const raw of Array.isArray(additions) ? additions : []) { const record = convert(raw); const key = recordId(record); if (key) map.set(key, record); }
  return [...map.values()];
}

function parseScalar(raw) {
  const value = String(raw || "").trim();
  if (!value) return "";
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) return value.slice(1, -1);
  return value;
}
function splitFrontmatter(text) {
  const lines = String(text).replace(/\r\n/g, "\n").split("\n");
  if (lines[0]?.trim() !== "---") return null;
  const end = lines.findIndex((line, i) => i > 0 && line.trim() === "---");
  if (end < 0) return null;
  const fm = {};
  for (const line of lines.slice(1, end)) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (match) fm[match[1]] = parseScalar(match[2]);
  }
  return { fm, body: lines.slice(end + 1).join("\n").replace(/^\s+|\s+$/g, "") };
}
function ignored(relative) {
  const parts = relative.split(/[\\/]/);
  return parts.some((part) => [".git", ".obsidian", "node_modules", ".trash", "target"].includes(part)) || parts[0] === "_control";
}
function walkMarkdown(root, current = root, output = []) {
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const absolute = path.join(current, entry.name);
    const relative = path.relative(root, absolute).replace(/\\/g, "/");
    if (ignored(relative)) continue;
    if (entry.isDirectory()) walkMarkdown(root, absolute, output);
    else if (entry.isFile() && /\.md$/i.test(entry.name)) output.push({ absolute, relative });
  }
  return output;
}
function localInstructions(root) {
  const bySlug = new Map();
  for (const file of walkMarkdown(root)) {
    const parsed = splitFrontmatter(fs.readFileSync(file.absolute, "utf8"));
    if (!parsed) continue;
    const kind = String(parsed.fm.record || parsed.fm.type || parsed.fm.kind || "").toLowerCase();
    if (kind !== "instruction") continue;
    const slug = String(parsed.fm.slug || "").trim();
    if (!slug) continue;
    if (bySlug.has(slug)) throw new Error(`Duplicate local instruction slug: ${slug}`);
    const stat = fs.statSync(file.absolute);
    const component = String(parsed.fm.component || parsed.fm.class || inferComponent(slug)).trim();
    const title = String(parsed.fm.title || parsed.fm.label || path.basename(file.relative, path.extname(file.relative))).trim();
    const description = String(parsed.fm.description || parsed.fm.summary || "").trim();
    bySlug.set(slug, {
      ui: { slug, record_identity: slug, title, label: title, description, scope: component, component, path: file.relative, source: "local" },
      config: { type: "instruction", identity: slug, content: parsed.body, extra: { title, description, scope: component, component, source_path: file.relative, source_modified_ns: String(BigInt(Math.round(stat.mtimeMs * 1e6))), source_size: stat.size } },
    });
  }
  return bySlug;
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
    childProcess.execFile(command, ["components", "snapshot"], { cwd: root, env: process.env, maxBuffer }, (error, stdout, stderr) => {
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

async function readPlanManagerSnapshot(root) {
  const local = localInstructions(root);
  const snapshot = await runComponentsSnapshot(root);
  const registries = snapshotRegistries(snapshot);
  const serverInstructions = registryRecords(registries.instructions, "slug");
  const plans = await listJsonAt(root, "plans", CONFIG_REF);
  const engines = registryRecords(registries.engines);
  const models = registryRecords(registries.models);
  const scripts = registryRecords(registries.local_scripts || registries.scripts);
  const ragProfiles = registryRecords(registries.rag_profiles);
  const instructions = overlayById(serverInstructions, [...local.values()].map((x) => x.ui), (x) => uiInstruction(x, "server"));
  const merged = overlayById(instructions, [...local.values()].map((x) => x.ui));
  return {
    catalogs: { instructions: merged, plans, engines, models, scripts, rag_profiles: ragProfiles },
    catalog: {
      source: "asc components snapshot",
      available: true,
      local_instructions: local.size,
      server_instructions: serverInstructions.length,
      engines: engines.length,
      models: models.length,
      scripts: scripts.length,
      rag_profiles: ragProfiles.length,
    },
  };
}

async function writeConfigSnapshot(root, record, { deletePlan = false } = {}) {
  const identity = safeIdentity(recordId(record));
  const locals = localInstructions(root);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const old = await revision(root, CONFIG_REF);
    const index = path.join(os.tmpdir(), `autoscribe-config-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.index`);
    try {
      const env = { GIT_INDEX_FILE: index };
      if (old) await runGit(root, ["read-tree", old], { env }); else await runGit(root, ["read-tree", "--empty"], { env });
      // A plan save is the publication snapshot: replace project-local instruction records with current working-tree versions.
      if (old) {
        const listing = await runGit(root, ["ls-tree", "-r", "--name-only", old, "--", "instructions/"], { allowFailure: true });
        for (const rel of String(listing.stdout).split(/\r?\n/).map((x) => x.trim()).filter(Boolean)) await runGit(root, ["update-index", "--force-remove", rel], { env });
      }
      for (const [slug, value] of locals) await stageJson(root, env, `instructions/${safeIdentity(slug)}.json`, value.config);
      const planPath = `plans/${identity}.json`;
      if (deletePlan) await runGit(root, ["update-index", "--force-remove", planPath], { env, allowFailure: true });
      else await stageJson(root, env, planPath, record);
      const tree = String((await runGit(root, ["write-tree"], { env })).stdout).trim();
      const commitArgs = ["commit-tree", tree]; if (old) commitArgs.push("-p", old);
      const verb = deletePlan ? "delete plan" : "plan";
      const commit = String((await runGit(root, commitArgs, { input: `AUTOSCRIBE CONFIG ${verb} ${identity}\n` })).stdout).trim();
      const expected = old || "0000000000000000000000000000000000000000";
      const update = await runGit(root, ["update-ref", "-m", "AutoScribe config publication", CONFIG_REF, commit, expected], { allowFailure: true });
      if (update.status !== 0) continue;
      await runGit(root, ["push", configRemote(), `${CONFIG_REF}:${CONFIG_REF}`]);
      return commit;
    } finally { try { await fs.promises.unlink(index); } catch {} }
  }
  throw new Error("AutoScribe config ref kept changing; save the plan again.");
}
async function stageJson(root, env, relativePath, value) {
  const bytes = `${JSON.stringify(value, null, 2)}\n`;
  const blob = String((await runGit(root, ["hash-object", "-w", "--stdin"], { input: bytes })).stdout).trim();
  await runGit(root, ["update-index", "--add", "--cacheinfo", "100644", blob, relativePath], { env });
}

async function savePlan(root, record) { return writeConfigSnapshot(root, record); }
async function deletePlan(root, identity) {
  const safeId = safeIdentity(identity);
  const existing = await readJsonAt(root, CONFIG_REF, `plans/${safeId}.json`);
  if (!existing) throw new Error(`Plan not found in ${CONFIG_REF}: ${safeId}`);
  return writeConfigSnapshot(root, existing, { deletePlan: true });
}

module.exports = { CONFIG_REF, listJsonAt, readJsonAt, readPlanManagerSnapshot, savePlan, deletePlan, localInstructions, runComponentsSnapshot };
