"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { loadConfig } = require("./config-loader");
const { expandHome, requireVaultBasePath } = require("./vault-paths.js");
function serviceConfig() { return loadConfig("service"); }
const vaultRoot = requireVaultBasePath;

function autoscribeRoot(app) {
  const cfg = serviceConfig();
  const envName = String(cfg.environment?.source_root || "AUTOSCRIBE_ROOT");
  if (process.env[envName]) return path.resolve(process.env[envName]);
  const controlMount = String(loadConfig("paths").control_mount || "_control");
  let candidate = fs.realpathSync(path.join(vaultRoot(app), controlMount));
  const marker = String(cfg.source_root_marker || "platform/service/Cargo.toml");
  for (let depth = 0; depth < Number(cfg.root_search_depth || 8); depth += 1) {
    if (fs.existsSync(path.join(candidate, ...marker.split("/")))) return candidate;
    const parent = path.dirname(candidate);
    if (parent === candidate) break;
    candidate = parent;
  }
  throw new Error(`Could not locate the source root; set ${envName}`);
}

function cargoTargetDir() {
  const cfg = serviceConfig();
  const envName = String(cfg.environment?.cargo_target_dir || "AUTOSCRIBE_CARGO_TARGET_DIR");
  return path.resolve(process.env[envName] || expandHome(cfg.cargo_target_default));
}

function newestServiceSourceMtime(serviceRoot) {
  let newest = 0;
  const visit = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile() && entry.name.endsWith(String(serviceConfig().source_extension || ".rs"))) {
        newest = Math.max(newest, fs.statSync(file).mtimeMs);
      }
    }
  };
  visit(path.join(serviceRoot, String(serviceConfig().source_dir || "src")));
  for (const name of (serviceConfig().source_manifest_files || [])) {
    const file = path.join(serviceRoot, name);
    if (fs.existsSync(file)) newest = Math.max(newest, fs.statSync(file).mtimeMs);
  }
  return newest;
}

function serviceCommand(app) {
  const root = autoscribeRoot(app);
  const cfg = serviceConfig();
  const explicit = process.env[String(cfg.environment?.service_binary || "SVC_BIN")];
  if (explicit) return { command: explicit, prefix: [] };

  const target = cargoTargetDir();
  const serviceRoot = path.join(root, ...String(cfg.service_relative_path || "platform/service").split("/"));
  const sourceMtime = newestServiceSourceMtime(serviceRoot);
  for (const profile of (cfg.build_profiles || [])) {
    const candidate = path.join(target, profile, String(cfg.service_binary_name || "svc"));
    if (!fs.existsSync(candidate)) continue;
    if (fs.statSync(candidate).mtimeMs >= sourceMtime) {
      return { command: candidate, prefix: [] };
    }
  }

  const cargo = expandHome(cfg.cargo_binary);
  const executable = fs.existsSync(cargo) ? cargo : String(cfg.cargo_fallback_command || "cargo");
  const manifest = path.join(serviceRoot, String(cfg.cargo_manifest || "Cargo.toml"));
  const args = (cfg.cargo_run_args || []).map((arg) => String(arg)
    .replace("{manifest}", manifest)
    .replace("{binary}", String(cfg.service_binary_name || "svc")));
  return {
    command: String(cfg.env_command || "/usr/bin/env"),
    prefix: [`${String(cfg.cargo_target_runtime_env || "CARGO_TARGET_DIR")}=${target}`, executable, ...args],
  };
}

function run(command, args, { cwd, input = "", env = {} } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, ...env },
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", (status) => {
      if (status === 0) resolve({ stdout, stderr });
      else reject(new Error((stderr || stdout || `exit status ${status}`).trim()));
    });
    child.stdin.end(input);
  });
}

function serviceEnvironment(app) {
  const root = autoscribeRoot(app);
  const cfg = serviceConfig();
  const env = cfg.environment || {};
  const databaseName = String(env.database || "AUTOSCRIBE_DATABASE");
  const filterName = String(env.pandoc_filter || "AUTOSCRIBE_PANDOC_FILTER");
  const parallelName = String(env.pandoc_parallelism || "AUTOSCRIBE_PANDOC_PARALLELISM");
  const pandocName = String(env.pandoc_bin || "PANDOC_BIN");
  return {
    [databaseName]: process.env[databaseName] || expandHome(cfg.database_default),
    [filterName]: process.env[filterName] || path.join(root, ...String(cfg.pandoc_filter_relative).split("/")),
    [parallelName]: String(Math.max(Number(cfg.pandoc_parallelism_min || 2), Number(process.env[parallelName]) || os.cpus().length)),
    [pandocName]: path.resolve(process.env[pandocName] || String(cfg.pandoc_bin_default || "/usr/bin/pandoc")),
  };
}

async function serviceCall(app, command, input) {
  const root = vaultRoot(app);
  const executable = serviceCommand(app);
  return run(executable.command, [...executable.prefix, command], {
    cwd: root,
    input: JSON.stringify(input),
    env: serviceEnvironment(app),
  });
}

async function runDispatch(app, { documents, plan }) {
  const selected = [...new Set((documents || []).map(String).map((value) => value.trim()).filter(Boolean))].sort();
  if (!selected.length) throw new Error("Dispatch requires document slugs");
  const protocol = loadConfig("protocol").dispatch || {};
  const response = await serviceCall(app, String(protocol.command || "dispatch-run"), {
    version: Number(protocol.request_version || 1),
    plan: String(plan || "").trim(),
    documents: selected,
  });
  const output = JSON.parse(response.stdout.trim() || "{}");
  if (!output.ok) throw new Error(output.error || "Rust dispatch run failed");
  return output;
}

module.exports = {
  autoscribeRoot,
  cargoTargetDir,
  run,
  runDispatch,
  serviceCall,
  serviceCommand,
  serviceEnvironment,
  vaultRoot,
};
