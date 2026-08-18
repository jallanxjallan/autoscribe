"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync, spawn } = require("node:child_process");
const { loadConfig } = require("./config-loader.js");
function feederConfig() { return loadConfig("feeder"); }
function pathsConfig() { return loadConfig("paths"); }
function expandHome(value) { return String(value || "").replace(/^\$HOME(?=\/|$)/, os.homedir()); }
function ipcArgs(vault) { return (feederConfig().ipc_args || []).map((arg) => String(arg).replace("{vault}", vault)); }

function vaultRoot(app) {
  const root = app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Obsidian vault adapter does not expose basePath");
  return path.resolve(root);
}

function candidateCommands() {
  const cfg = feederConfig();
  const env = cfg.environment || {};
  return [
    process.env[String(env.primary_bin || "OBSIDIAN_FEEDER_BIN")],
    process.env[String(env.secondary_bin || "OBS_BIN")],
    ...(cfg.candidate_commands || []).map(expandHome),
  ].filter(Boolean);
}

function resolveCommand() {
  for (const command of candidateCommands()) {
    if (command === "obs" || fs.existsSync(command)) return command;
  }
  throw new Error(`Could not locate feeder command; set ${String(feederConfig().environment?.primary_bin || "OBSIDIAN_FEEDER_BIN")}`);
}

function callFeeder(app, operation, payload = {}) {
  const request = { ...payload, operation, vault: payload.vault || vaultRoot(app) };
  const command = resolveCommand();
  const result = spawnSync(command, ipcArgs(request.vault), {
    cwd: request.vault,
    input: JSON.stringify(request),
    encoding: "utf8",
    shell: false,
    maxBuffer: Number(feederConfig().max_buffer_bytes || 33554432),
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
    const child = spawn(command, ipcArgs(request.vault), {
      cwd: request.vault,
      encoding: "utf8",
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const stdout = [];
    const stderr = [];
    let stdoutBytes = 0;
    const maxBuffer = Number(feederConfig().max_buffer_bytes || 33554432);

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
  const statusDir = path.join(vault, String(pathsConfig().runtime_dir || ".autoscribe"), String(pathsConfig().system_status_dir || "system-status"));
  fs.mkdirSync(statusDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const requestPath = path.join(statusDir, `${stamp}-${operation.replace(/[^a-z0-9_.-]/gi, "_")}.request.json`);
  const stdoutPath = requestPath.replace(/\.request\.json$/, ".stdout.log");
  const stderrPath = requestPath.replace(/\.request\.json$/, ".stderr.log");
  fs.writeFileSync(requestPath, JSON.stringify(request, null, 2) + "\n", "utf8");
  const input = fs.openSync(requestPath, "r");
  const stdout = fs.openSync(stdoutPath, "a");
  const stderr = fs.openSync(stderrPath, "a");
  const child = spawn(command, ipcArgs(vault), {
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
