"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

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

module.exports = { callFeeder, vaultRoot };
