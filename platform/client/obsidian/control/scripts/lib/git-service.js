"use strict";
const { serviceCall } = require("./dispatch-service.js");
const { loadConfig } = require("./config-loader.js");
const { requireVaultBasePath } = require("./vault-paths.js");

const vaultRoot = requireVaultBasePath;

async function gitFiles(app, action, request = {}) {
  const spec = loadConfig("protocol").service_operations?.git_files || {};
  const input = { version: Number(spec.request_version), action, ...request };
  const response = await serviceCall(app, String(spec.command), input);
  const output = JSON.parse(response.stdout.trim() || "{}");
  if (!output.ok) throw new Error(output.error || `Rust Git operation failed: ${action}`);
  return output;
}

module.exports = { gitFiles, vaultRoot };
