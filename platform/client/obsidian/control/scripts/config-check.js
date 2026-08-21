#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { loadConfig } = require("./lib/config-loader.js");

const CONTROL_ROOT = path.resolve(__dirname, "..");
const CONFIG_DIR = path.join(CONTROL_ROOT, "config");
const CONFIG_NAMES = fs.readdirSync(CONFIG_DIR)
  .filter((name) => name.toLowerCase().endsWith(".yaml"))
  .map((name) => name.replace(/\.ya?ml$/i, ""))
  .sort();

const errors = [];
const warnings = [];
const ok = (message) => console.log(`OK   ${message}`);
const warn = (message) => { warnings.push(message); console.warn(`WARN ${message}`); };
const fail = (message) => { errors.push(message); console.error(`FAIL ${message}`); };

function controlPath(vaultRelative) {
  const mount = String(loadConfig("paths").control_mount || "_control").replace(/^\/+|\/+$/g, "");
  const value = String(vaultRelative || "").replace(/^\/+/, "");
  const relative = value === mount ? "" : value.startsWith(`${mount}/`) ? value.slice(mount.length + 1) : value;
  return path.join(CONTROL_ROOT, ...relative.split("/").filter(Boolean));
}

function duplicates(values) {
  const seen = new Set();
  const dupes = new Set();
  for (const value of values) {
    const key = String(value);
    if (seen.has(key)) dupes.add(key);
    seen.add(key);
  }
  return [...dupes];
}

for (const name of CONFIG_NAMES) {
  try {
    loadConfig(name);
    ok(`config/${name}.yaml parses`);
  } catch (error) {
    fail(`config/${name}.yaml: ${error.message}`);
  }
}

if (!errors.length) {
  const vocab = loadConfig("vocabulary");
  for (const field of ["stage", "status", "action", "origin", "producer"]) {
    const values = vocab[field] || [];
    const dupes = duplicates(values);
    if (dupes.length) fail(`vocabulary.${field} contains duplicates: ${dupes.join(", ")}`);
  }

  const stage = new Set((vocab.stage || []).map(String));
  const status = new Set((vocab.status || []).map(String));
  const exactOverlap = [...stage].filter((value) => status.has(value));
  if (exactOverlap.length) warn(`stage/status exact overlap: ${exactOverlap.join(", ")}`);

  const records = loadConfig("records");
  for (const [groupId, group] of Object.entries(records.groups || {})) {
    for (const [choiceId, choice] of Object.entries(group.choices || {})) {
      if (Object.prototype.hasOwnProperty.call(choice, "prefix") && !String(choice.prefix || "").trim()) {
        fail(`records.${groupId}.${choiceId}.prefix is blank; omit prefix for non-slug note types`);
      }
      const template = controlPath(choice.template);
      if (!fs.existsSync(template)) fail(`records.${groupId}.${choiceId} template not found: ${choice.template}`);
      const defaults = choice.defaults || {};
      if (defaults.stage != null && !stage.has(String(defaults.stage))) {
        warn(`records.${groupId}.${choiceId}.defaults.stage=${defaults.stage} is outside vocabulary.stage`);
      }
      if (defaults.status != null && !status.has(String(defaults.status))) {
        warn(`records.${groupId}.${choiceId}.defaults.status=${defaults.status} is outside vocabulary.status`);
      }
      for (const field of ["action", "origin", "producer"]) {
        if (defaults[field] == null) continue;
        const allowed = new Set((vocab[field] || []).map(String));
        if (allowed.size && !allowed.has(String(defaults[field]))) {
          warn(`records.${groupId}.${choiceId}.defaults.${field}=${defaults[field]} is outside vocabulary.${field}`);
        }
      }
    }
  }

  const editorial = records.editorial_note?.defaults || {};
  if (editorial.status != null && !status.has(String(editorial.status))) {
    warn(`records.editorial_note.defaults.status=${editorial.status} is outside vocabulary.status`);
  }
  if (editorial.action != null && !(vocab.action || []).map(String).includes(String(editorial.action))) {
    warn(`records.editorial_note.defaults.action=${editorial.action} is outside vocabulary.action`);
  }

  const annotations = loadConfig("annotations");
  const annotationTypes = annotations.types || {};
  for (const [role, id] of Object.entries(annotations.roles || {})) {
    if (!annotationTypes[id]) fail(`annotations.roles.${role} points to missing type '${id}'`);
  }

  const instructions = loadConfig("instructions");
  const componentPrefixes = Object.values(instructions.instruction_components || {}).map((item) => String(item.prefix || ""));
  const duplicatePrefixes = duplicates(componentPrefixes.filter(Boolean));
  if (duplicatePrefixes.length) fail(`instructions.instruction_components has duplicate prefixes: ${duplicatePrefixes.join(", ")}`);

  const dashboard = loadConfig("dashboard");
  for (const [id, action] of Object.entries(dashboard.actions || {})) {
    const file = controlPath(action.macro);
    if (!fs.existsSync(file)) fail(`dashboard.actions.${id}.macro not found: ${action.macro}`);
  }

  const workflow = loadConfig("workflow");
  const writeback = workflow.writeback || {};
  if (writeback.status != null && !status.has(String(writeback.status))) {
    warn(`workflow.writeback.status=${writeback.status} is outside vocabulary.status`);
  }
  if (writeback.producer != null && !(vocab.producer || []).map(String).includes(String(writeback.producer))) {
    warn(`workflow.writeback.producer=${writeback.producer} is outside vocabulary.producer`);
  }

  const maintenance = loadConfig("maintenance");
  for (const relative of maintenance.deprecated_files || []) {
    if (fs.existsSync(path.join(CONTROL_ROOT, String(relative)))) warn(`deprecated file still present: ${relative}`);
  }
}

console.log("");
console.log(`${errors.length} error(s), ${warnings.length} warning(s).`);
if (warnings.length) console.log("Warnings are schema decisions for manual review; they do not block Control.");
process.exit(errors.length ? 1 : 0);
