"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { sanitizeForPath } = require("./text");
const {
  getVaultBasePath,
  getVaultName,
  getActiveQueryPath,
} = require("./query-runtime");

function shortHash(text) {
  return crypto
    .createHash("sha1")
    .update(String(text))
    .digest("hex")
    .slice(0, 8);
}

function getVaultKeyFromRoot(root, name = "vault") {
  if (!root || typeof root !== "string") {
    throw new Error("getVaultKeyFromRoot requires a vault root path string.");
  }

  const base = name === "vault" ? path.basename(root) || name : name;
  return `${sanitizeForPath(base)}-${shortHash(path.resolve(root))}`;
}

function getVaultKey(app) {
  return getVaultKeyFromRoot(getVaultBasePath(app), getVaultName(app));
}

function getAutoscribeDir(app) {
  const vaultRoot = getVaultBasePath(app);
  if (!vaultRoot || typeof vaultRoot !== "string") {
    throw new Error("getAutoscribeDir requires an active vault root.");
  }
  return path.join(vaultRoot, ".autoscribe");
}

function getSelectionsDir(app) {
  return path.join(getAutoscribeDir(app), "selections");
}

function getManifestPath(app, operation) {
  if (!app) {
    throw new Error("getManifestPath requires app.");
  }
  if (!operation || typeof operation !== "string") {
    throw new Error("getManifestPath requires operation.");
  }

  return path.join(
    getSelectionsDir(app),
    `${sanitizeForPath(operation)}.json`
  );
}

function readManifest(app, operation) {
  const manifestPath = getManifestPath(app, operation);

  try {
    return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function writeJsonFile(file, data) {
  if (!file || typeof file !== "string") {
    throw new Error("writeJsonFile requires a file path string.");
  }

  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  return file;
}

function normalizeWriteArgs(args) {
  if (args.length === 1 && args[0] && typeof args[0] === "object") {
    return args[0];
  }

  const [app, operation, manifest] = args;
  return { app, operation, manifest };
}

function buildManifest({
  app,
  operation,
  queryName,
  namespace,
  options = {},
  items = [],
  manifest,
  extra = {},
}) {
  if (manifest !== undefined) {
    if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
      throw new Error("writeManifest manifest must be an object.");
    }

    return manifest;
  }

  if (!Array.isArray(items)) {
    throw new Error("writeManifest items must be an array.");
  }

  const timestamp = new Date().toISOString();
  const vaultRoot = getVaultBasePath(app);
  const vaultName = getVaultName(app);
  const vaultKey = getVaultKeyFromRoot(vaultRoot, vaultName);
  let queryPath = "";

  try {
    queryPath = getActiveQueryPath(app);
  } catch (_) {}

  return {
    type: "operation_manifest",
    recordType: "operation_manifest",

    timestamp,
    savedAt: timestamp,
    saved_at: timestamp,

    operation,
    queryName: queryName || operation,
    namespace: namespace || operation,

    vaultName,
    vault: vaultName,
    vaultRoot,
    vaultKey,
    vault_info: {
      name: vaultName,
      root: vaultRoot,
      key: vaultKey,
    },
    queryPath,

    options: options && typeof options === "object" && !Array.isArray(options)
      ? options
      : {},

    count: items.length,
    items,

    ...extra,
  };
}

function writeManifest(...args) {
  const params = normalizeWriteArgs(args);
  const { app, operation } = params;

  if (!app) throw new Error("writeManifest requires app.");
  if (!operation) throw new Error("writeManifest requires operation.");

  const manifestPath = getManifestPath(app, operation);
  const manifest = buildManifest(params);

  writeJsonFile(manifestPath, manifest);

  return { manifestPath, manifest };
}

module.exports = {
  shortHash,
  getVaultKeyFromRoot,
  getVaultKey,
  getAutoscribeDir,
  getSelectionsDir,
  getManifestPath,
  readManifest,
  writeJsonFile,
  buildManifest,
  writeManifest,
};
