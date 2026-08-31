"use strict";

const childProcess = require("node:child_process");
const fs = require("node:fs");
const { loadConfig } = require("./config-loader");

function workflow() { return loadConfig("workflow").plan_manager || {}; }
function configured(key, envKey, fallback) {
  const fromEnv = String(process.env[envKey] || "").trim();
  if (fromEnv) return fromEnv;
  return String(workflow()[key] || fallback || "").trim();
}
function ascCommand() {
  const command = configured("asc_command", "AUTOSCRIBE_ASC", "");
  if (command) return command;
  const local = "/home/jeremy/Python3.13Env/bin/asc";
  return fs.existsSync(local) ? local : "asc";
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

function runAsc(args, { input = null, cwd = process.cwd() } = {}) {
  return new Promise((resolve, reject) => {
    const child = childProcess.spawn(ascCommand(), args, {
      cwd,
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stdout = [], stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (status) => {
      const out = Buffer.concat(stdout).toString("utf8");
      const err = Buffer.concat(stderr).toString("utf8");
      if (status === 0) resolve(out);
      else reject(new Error(String(err || out || `asc exited with status ${status}`).trim()));
    });
    child.stdin.end(input == null ? undefined : input);
  });
}

async function readPlanManagerSnapshot(vaultRoot) {
  const raw = await runAsc(["control", "snapshot"], { cwd: vaultRoot || process.cwd() });
  let snapshot;
  try { snapshot = JSON.parse(raw || "{}"); }
  catch (error) { throw new Error(`asc control snapshot returned invalid JSON: ${error.message || error}`); }
  const registries = snapshot?.registries && typeof snapshot.registries === "object" ? snapshot.registries : {};
  const instructions = registryRecords(registries.instructions, "slug");
  const plans = registryRecords(registries.plans, "record_identity");
  const engines = registryRecords(registries.engines);
  const models = registryRecords(registries.models);
  const scripts = registryRecords(registries.local_scripts || registries.scripts);
  const ragProfiles = registryRecords(registries.rag_profiles);
  return {
    catalogs: { instructions, plans, engines, models, scripts, rag_profiles: ragProfiles },
    catalog: {
      source: "published server Git",
      available: true,
      committed_instructions: instructions.length,
      plans: plans.length,
      unpublished: false,
      engines: engines.length,
      models: models.length,
      scripts: scripts.length,
      rag_profiles: ragProfiles.length,
    },
  };
}

async function readPlans(vaultRoot, scope = "") {
  const args = ["control", "plans"];
  const cleanScope = String(scope || "").trim();
  if (cleanScope) args.push("--scope", cleanScope);
  const raw = await runAsc(args, { cwd: vaultRoot || process.cwd() });
  let records;
  try { records = JSON.parse(raw || "[]"); }
  catch (error) { throw new Error(`asc control plans returned invalid JSON: ${error.message || error}`); }
  if (!Array.isArray(records)) throw new Error("asc control plans did not return a JSON array");
  return records;
}

async function savePlan(vaultRoot, record) {
  const raw = await runAsc(["control", "save-plan"], {
    cwd: vaultRoot || process.cwd(),
    input: `${JSON.stringify(record)}\n`,
  });
  const result = JSON.parse(raw || "{}");
  return String(result.commit || "");
}

async function deletePlan(vaultRoot, identity) {
  const raw = await runAsc(["control", "delete-plan", String(identity || "").trim()], {
    cwd: vaultRoot || process.cwd(),
  });
  const result = JSON.parse(raw || "{}");
  return String(result.commit || "");
}

module.exports = {
  readPlanManagerSnapshot,
  readPlans,
  savePlan,
  deletePlan,
  runAsc,
};
