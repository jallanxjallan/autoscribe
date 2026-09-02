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
  return path.resolve(expandHome(cfg.source_root));
}

function serviceCommand() {
  const cfg = serviceConfig();
  const command = path.resolve(expandHome(cfg.service_binary));
  if (!fs.existsSync(command)) {
    throw new Error(`Rust service binary not found: ${command}. Re-run the Control installer.`);
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
  // AutoScribe configuration is compiled/configured inside the platform tree.
  // Preserve the ambient environment only so provider credentials remain available.
  return {};
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
