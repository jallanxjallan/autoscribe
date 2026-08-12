"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { vaultRoot } = require("../lib/vault-state.js");

const PLAN_DIR = "_plans";
const PLAN_SLUG_RE = /^plan\.[a-z0-9][a-z0-9.-]*$/;

function repositoryRoot(app) {
  const base = vaultRoot(app);
  try {
    return execFileSync("git", ["-C", base, "rev-parse", "--show-toplevel"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim() || base;
  } catch {
    return base;
  }
}

function planDir(app) {
  return path.join(repositoryRoot(app), PLAN_DIR);
}

function assertPlanSlug(slug) {
  const value = String(slug || "").trim();
  if (!PLAN_SLUG_RE.test(value)) throw new Error(`Invalid plan slug: ${value || "<empty>"}`);
  return value;
}

function planPath(app, slug) {
  return path.join(planDir(app), `${assertPlanSlug(slug)}.json`);
}

function parsePlanFile(file) {
  let record;
  try {
    record = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    throw new Error(`${file}: invalid JSON plan: ${error.message}`);
  }
  if (!record || typeof record !== "object" || Array.isArray(record)) {
    throw new Error(`${file}: plan JSON must be an object`);
  }
  const slug = assertPlanSlug(record.record_identity || record.slug);
  if (path.basename(file) !== `${slug}.json`) {
    throw new Error(`${file}: filename must be ${slug}.json`);
  }
  return { ...record, record_type: "plan", record_identity: slug, slug, path: file };
}

function listPlanRecords(app) {
  const dir = planDir(app);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".json"))
    .map((entry) => parsePlanFile(path.join(dir, entry.name)))
    .sort((a, b) => String(a.payload?.label || a.label || a.slug)
      .localeCompare(String(b.payload?.label || b.label || b.slug)));
}

function loadPlanRecord(app, slug) {
  const target = planPath(app, slug);
  if (!fs.existsSync(target)) throw new Error(`Plan not found: ${assertPlanSlug(slug)}`);
  return parsePlanFile(target);
}

function savePlanRecord(app, record) {
  const slug = assertPlanSlug(record.record_identity || record.slug);
  const dir = planDir(app);
  fs.mkdirSync(dir, { recursive: true });
  const target = planPath(app, slug);
  const envelope = {
    record_type: "plan",
    record_identity: slug,
    payload: record.payload,
  };
  fs.writeFileSync(target, `${JSON.stringify(envelope, null, 2)}\n`, "utf8");
  if (!fs.existsSync(target)) throw new Error(`Plan write did not create ${target}`);
  return target;
}

function deletePlanRecord(app, slug) {
  const target = planPath(app, slug);
  if (!fs.existsSync(target)) throw new Error(`Plan not found: ${assertPlanSlug(slug)}`);
  fs.unlinkSync(target);
  return target;
}

module.exports = { repositoryRoot, planDir, planPath, listPlanRecords, loadPlanRecord, savePlanRecord, deletePlanRecord };
