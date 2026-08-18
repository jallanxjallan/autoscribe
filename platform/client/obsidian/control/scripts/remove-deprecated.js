#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { loadConfig } = require("./lib/config-loader.js");

const CONTROL_ROOT = path.resolve(__dirname, "..");
const deprecated = loadConfig("maintenance").deprecated_files || [];

for (const value of deprecated) {
  const relative = String(value || "").replace(/\\/g, "/");
  if (!relative || relative.startsWith("/") || relative.split("/").includes("..")) {
    throw new Error(`Unsafe deprecated path in config/maintenance.yaml: ${value}`);
  }
  const target = path.resolve(CONTROL_ROOT, relative);
  if (target !== CONTROL_ROOT && !target.startsWith(`${CONTROL_ROOT}${path.sep}`)) {
    throw new Error(`Deprecated path escapes control root: ${value}`);
  }
  if (!fs.existsSync(target)) continue;
  fs.rmSync(target, { recursive: true, force: true });
  console.log(`Removed deprecated: ${relative}`);
}
