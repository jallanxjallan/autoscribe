"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Obsidian vault adapter does not expose its base path");
  return path.resolve(root);
}

function autoscribeRoot(app) {
  if (process.env.AUTOSCRIBE_ROOT) return path.resolve(process.env.AUTOSCRIBE_ROOT);
  let candidate = fs.realpathSync(path.join(vaultRoot(app), "_control"));
  for (let depth = 0; depth < 8; depth += 1) {
    if (fs.existsSync(path.join(candidate, "platform", "service", "Cargo.toml"))) return candidate;
    const parent = path.dirname(candidate);
    if (parent === candidate) break;
    candidate = parent;
  }
  throw new Error("Could not locate the AutoScribe source root; set AUTOSCRIBE_ROOT");
}

function cargoTargetDir() {
  return path.resolve(
    process.env.AUTOSCRIBE_CARGO_TARGET_DIR ||
    path.join(os.homedir(), ".cache", "autoscribe", "cargo", "service")
  );
}

function newestServiceSourceMtime(serviceRoot) {
  let newest = 0;
  const visit = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile() && entry.name.endsWith(".rs")) {
        newest = Math.max(newest, fs.statSync(file).mtimeMs);
      }
    }
  };
  visit(path.join(serviceRoot, "src"));
  for (const name of ["Cargo.toml", "Cargo.lock"]) {
    const file = path.join(serviceRoot, name);
    if (fs.existsSync(file)) newest = Math.max(newest, fs.statSync(file).mtimeMs);
  }
  return newest;
}

function serviceCommand(app) {
  const root = autoscribeRoot(app);
  const explicit = process.env.SVC_BIN;
  if (explicit) return { command: explicit, prefix: [] };

  const target = cargoTargetDir();
  const serviceRoot = path.join(root, "platform", "service");
  const sourceMtime = newestServiceSourceMtime(serviceRoot);
  for (const profile of ["release", "debug"]) {
    const candidate = path.join(target, profile, "svc");
    if (!fs.existsSync(candidate)) continue;
    if (fs.statSync(candidate).mtimeMs >= sourceMtime) {
      return { command: candidate, prefix: [] };
    }
  }

  const cargo = path.join(os.homedir(), ".cargo", "bin", "cargo");
  const executable = fs.existsSync(cargo) ? cargo : "cargo";
  const manifest = path.join(serviceRoot, "Cargo.toml");
  return {
    command: "/usr/bin/env",
    prefix: [
      `CARGO_TARGET_DIR=${target}`,
      executable,
      "run",
      "--quiet",
      "--manifest-path",
      manifest,
      "--bin",
      "svc",
      "--",
    ],
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
  return {
    AUTOSCRIBE_DATABASE:
      process.env.AUTOSCRIBE_DATABASE ||
      path.join(os.homedir(), ".local", "share", "autoscribe", "service.sqlite"),
    AUTOSCRIBE_PANDOC_FILTER:
      process.env.AUTOSCRIBE_PANDOC_FILTER ||
      path.join(root, "platform", "pandoc", "filters", "emit", "emit_ndjson.lua"),
    AUTOSCRIBE_PANDOC_PARALLELISM: String(
      Math.max(2, Number(process.env.AUTOSCRIBE_PANDOC_PARALLELISM) || os.cpus().length)
    ),
    PANDOC_BIN: path.resolve(process.env.PANDOC_BIN || "/usr/bin/pandoc"),
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
  const response = await serviceCall(app, "dispatch-run", {
    version: 1,
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
