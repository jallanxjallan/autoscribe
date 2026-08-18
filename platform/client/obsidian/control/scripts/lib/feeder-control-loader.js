"use strict";
const { callFeeder } = require("./feeder-ipc.js");
const { loadConfig } = require("./config-loader.js");
function ops() { return loadConfig("protocol").feeder_operations || {}; }

function loadRegistrySnapshot(app) {
  try { const spec = ops().registry_snapshot || {}; return { data: callFeeder(app, String(spec.command), { kind: String(spec.kind) }), error: null }; }
  catch (error) { return { data: null, error: error.message, stderr: "", stdout: "" }; }
}
function loadControlSnapshot(app) {
  try { const spec = ops().control_snapshot || {}; return { data: callFeeder(app, String(spec.command), { kind: String(spec.kind) }), error: null }; }
  catch (error) { return { data: null, error: error.message, stderr: "", stdout: "" }; }
}
function snapshotList(snapshot, name) {
  return Object.entries(snapshot?.registries?.[name] || {}).map(([registryKey, value]) => {
    const record = value && typeof value === "object" && !Array.isArray(value) ? { ...value } : { value };
    return {
      ...record,
      registry_key: registryKey,
      key: String(record.key || record.slug || record.record_identity || registryKey),
    };
  });
}
function listInstructions(app) { const spec = ops().instructions_catalog || {}; return callFeeder(app, String(spec.command), { include_pipeline: spec.include_pipeline === true }); }
function listControls(app) { return listInstructions(app); }
function controlWarnings(records) {
  const warnings = [];
  const dirty = records.filter((r) => r.repo_state && r.repo_state !== "clean" && r.source === "active").length;
  const missing = records.filter((r) => r.source === "active" && r.has_prior_commit === false).length;
  if (dirty) warnings.push(`${dirty} selected control file(s) are dirty`);
  if (missing) warnings.push(`${missing} selected control file(s) have no prior commit`);
  return warnings;
}
module.exports = { loadRegistrySnapshot, loadControlSnapshot, snapshotList, listInstructions, listControls, controlWarnings };
