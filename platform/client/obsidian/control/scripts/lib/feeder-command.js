"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { requireVaultBasePath } = require("./vault-paths.js");
const { spawn } = require("node:child_process");

const vaultRoot = requireVaultBasePath;

function candidateCommands() {
  return [
    process.env.OBSIDIAN_FEEDER_BIN,
    process.env.OBS_BIN,
    path.join(os.homedir(), "Python3.13Env", "bin", "obs"),
    path.join(os.homedir(), ".local", "bin", "obs"),
    "/usr/local/bin/obs",
    "/usr/bin/obs",
    "obs",
  ].filter(Boolean);
}

function resolveCommand() {
  for (const command of candidateCommands()) {
    if (command === "obs" || fs.existsSync(command)) return command;
  }
  throw new Error("Could not locate feeder command; set OBSIDIAN_FEEDER_BIN");
}

function runFeederCommand(app, args, { detached = false } = {}) {
  const cwd = vaultRoot(app);
  const command = resolveCommand();
  const argv = [...args];

  if (detached) {
    return new Promise((resolve, reject) => {
      const child = spawn(command, argv, {
        cwd,
        detached: true,
        stdio: "ignore",
        env: process.env,
        shell: false,
      });
      child.once("error", reject);
      child.once("spawn", () => {
        child.unref();
        resolve({ pid: child.pid, command, args: argv, cwd, detached: true });
      });
    });
  }

  return new Promise((resolve, reject) => {
    const child = spawn(command, argv, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: process.env,
      shell: false,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.on("error", reject);
    child.on("close", (status) => {
      const result = { status, stdout, stderr, command, args: argv, cwd, detached: false };
      if (status !== 0) {
        const detail = stderr.trim() || stdout.trim() || `exit status ${status}`;
        const error = new Error(`obs ${argv.join(" ")} failed: ${detail}`);
        error.result = result;
        reject(error);
        return;
      }
      resolve(result);
    });
  });
}

module.exports = { runFeederCommand, vaultRoot };
