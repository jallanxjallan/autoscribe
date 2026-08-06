"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync, spawn } = require("node:child_process");

function vaultRoot(app) {
  const root = app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Obsidian vault adapter does not expose basePath");
  return path.resolve(root);
}

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

function callFeeder(app, operation, payload = {}) {
  const request = { ...payload, operation, vault: payload.vault || vaultRoot(app) };
  const command = resolveCommand();
  const result = spawnSync(command, ["--vault", request.vault, "ipc"], {
    cwd: request.vault,
    input: JSON.stringify(request),
    encoding: "utf8",
    shell: false,
    maxBuffer: 32 * 1024 * 1024,
  });
  const stdout = String(result.stdout || "").trim();
  const stderr = String(result.stderr || "").trim();
  if (result.error) throw result.error;
  let response;
  try { response = JSON.parse(stdout); }
  catch (error) {
    throw new Error(`Feeder IPC returned invalid JSON: ${error.message}${stderr ? `\n${stderr}` : ""}`);
  }
  if (result.status !== 0 || !response?.ok) {
    throw new Error(response?.error || stderr || `Feeder IPC failed with status ${result.status}`);
  }
  return response.result;
}

function callFeederAsync(app, operation, payload = {}) {
  const request = { ...payload, operation, vault: payload.vault || vaultRoot(app) };
  const command = resolveCommand();

  return new Promise((resolve, reject) => {
    const child = spawn(command, ["--vault", request.vault, "ipc"], {
      cwd: request.vault,
      encoding: "utf8",
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const stdout = [];
    const stderr = [];
    let stdoutBytes = 0;
    const maxBuffer = 32 * 1024 * 1024;

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdoutBytes += Buffer.byteLength(chunk);
      if (stdoutBytes > maxBuffer) {
        child.kill();
        reject(new Error("Feeder IPC output exceeded 32 MiB"));
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", reject);
    child.once("close", (status) => {
      const output = stdout.join("").trim();
      const errors = stderr.join("").trim();
      let response;
      try { response = JSON.parse(output); }
      catch (error) {
        reject(new Error(`Feeder IPC returned invalid JSON: ${error.message}${errors ? `\n${errors}` : ""}`));
        return;
      }
      if (status !== 0 || !response?.ok) {
        reject(new Error(response?.error || errors || `Feeder IPC failed with status ${status}`));
        return;
      }
      resolve(response.result);
    });

    child.stdin.end(JSON.stringify(request));
  });
}

function handoffFeeder(app, operation, payload = {}) {
  const vault = payload.vault || vaultRoot(app);
  const request = { ...payload, operation, vault };
  const command = resolveCommand();
  const statusDir = path.join(vault, ".autoscribe", "system-status");
  fs.mkdirSync(statusDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const requestPath = path.join(statusDir, `${stamp}-${operation.replace(/[^a-z0-9_.-]/gi, "_")}.request.json`);
  const stdoutPath = requestPath.replace(/\.request\.json$/, ".stdout.log");
  const stderrPath = requestPath.replace(/\.request\.json$/, ".stderr.log");
  fs.writeFileSync(requestPath, JSON.stringify(request, null, 2) + "\n", "utf8");
  const input = fs.openSync(requestPath, "r");
  const stdout = fs.openSync(stdoutPath, "a");
  const stderr = fs.openSync(stderrPath, "a");
  const child = spawn(command, ["--vault", vault, "ipc"], {
    cwd: vault,
    detached: true,
    stdio: [input, stdout, stderr],
    env: process.env,
  });
  child.unref();
  fs.closeSync(input); fs.closeSync(stdout); fs.closeSync(stderr);
  return { pid: child.pid, request_path: requestPath, stdout_path: stdoutPath, stderr_path: stderrPath };
}

module.exports = { callFeeder, callFeederAsync, handoffFeeder, vaultRoot };
