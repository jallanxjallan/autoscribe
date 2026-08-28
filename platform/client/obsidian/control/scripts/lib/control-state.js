"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { loadConfig } = require("./config-loader.js");
const { requireVaultBasePath } = require("./vault-paths.js");

function managerConfig() {
  return loadConfig("workflow").plan_manager || {};
}

function controlStatePaths(app) {
  const base = requireVaultBasePath(app);
  const stateDir = String(managerConfig().state_dir || ".autoscribe");
  return {
    state: path.join(base, stateDir, String(managerConfig().state_file || "control-state.json")),
    plans: path.join(base, stateDir, String(managerConfig().plan_dir || "plans")),
  };
}

async function readControlState(app) {
  const paths = controlStatePaths(app);
  let text;
  try {
    text = await fs.promises.readFile(paths.state, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error("Plan catalogue is not initialized. Run 'svc refresh' from the vault root first.");
    }
    throw error;
  }

  // Yield once after I/O so opening a workflow never monopolizes the renderer
  // merely because the catalogue was read from disk synchronously.
  await new Promise((resolve) => setTimeout(resolve, 0));

  const state = JSON.parse(text);
  if (Number(state.version || 0) !== 1) {
    throw new Error("Unsupported AutoScribe control-state version.");
  }
  return state;
}

function catalogsFromState(state) {
  const source = state?.catalogs || {};
  return {
    instructions: Array.isArray(source.instructions) ? source.instructions : [],
    plans: Array.isArray(source.plans) ? source.plans : [],
    engines: Array.isArray(source.engines) ? source.engines : [],
    models: Array.isArray(source.models) ? source.models : [],
    scripts: Array.isArray(source.scripts) ? source.scripts : [],
    ragProfiles: Array.isArray(source.rag_profiles) ? source.rag_profiles : [],
  };
}

async function writePlanDraft(app, record, slug) {
  const paths = controlStatePaths(app);
  await fs.promises.mkdir(paths.plans, { recursive: true });

  const safeSlug = String(slug || "").trim();
  if (!/^[a-z0-9][a-z0-9._-]*$/i.test(safeSlug)) {
    throw new Error(`Unsafe plan slug: ${safeSlug}`);
  }

  const target = path.join(paths.plans, `${safeSlug}.json`);
  const temp = `${target}.tmp-${process.pid}-${Date.now()}`;
  await fs.promises.writeFile(temp, `${JSON.stringify(record, null, 2)}\n`, "utf8");
  try {
    await fs.promises.rename(temp, target);
  } catch (error) {
    await fs.promises.rm(temp, { force: true }).catch(() => {});
    throw error;
  }
  return target;
}

module.exports = {
  catalogsFromState,
  controlStatePaths,
  readControlState,
  writePlanDraft,
};
