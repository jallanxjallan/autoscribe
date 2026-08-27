"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { loadConfig } = require("./config-loader");
const { expandHome, requireVaultBasePath } = require("./vault-paths.js");

function serviceConfig() { return loadConfig("service"); }
const vaultRoot = requireVaultBasePath;

function autoscribeRoot() {
  const cfg = serviceConfig();
  const envName = String(cfg.environment?.source_root || "AUTOSCRIBE_ROOT");
  return path.resolve(process.env[envName] || expandHome(cfg.source_root_default));
}

function serviceCommand() {
  const cfg = serviceConfig();
  const envName = String(cfg.environment?.service_binary || "SVC_BIN");
  const command = path.resolve(process.env[envName] || expandHome(cfg.service_binary_default));
  if (!fs.existsSync(command)) {
    throw new Error(`Rust service binary not found: ${command}. Re-run the Control installer or set ${envName}.`);
  }
  return command;
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

function serviceEnvironment() {
  const root = autoscribeRoot();
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
  return run(serviceCommand(), [command], {
    cwd: vaultRoot(app),
    input: JSON.stringify(input),
    env: serviceEnvironment(),
  });
}

module.exports = {
  autoscribeRoot,
  run,
  serviceCall,
  serviceCommand,
  serviceEnvironment,
  vaultRoot,
};
