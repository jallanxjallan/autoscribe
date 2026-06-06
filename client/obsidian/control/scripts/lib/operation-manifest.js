"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { sanitizeForPath } = require("./text");
const {
  getVaultBasePath,
  getVaultName,
} = require("./query-runtime");

function autoscribeHome() {
  return (
    process.env.AUTOSCRIBE_HOME ||
    process.env.AUTOSCRIBE_DATA_ROOT ||
    path.join(os.homedir(), ".local", "share", "autoscribe")
  );
}

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

function getOperationDirFromVaultKey({ vaultKey, group = "selections" }) {
  if (!vaultKey || typeof vaultKey !== "string") {
    throw new Error("getOperationDirFromVaultKey requires vaultKey.");
  }
  if (!group || typeof group !== "string") {
    throw new Error("getOperationDirFromVaultKey requires group.");
  }
  return path.join(autoscribeHome(), "obsidian", "vaults", vaultKey, sanitizeForPath(group));
}

function getOperationPathFromVaultKey({ vaultKey, group = "selections", name }) {
  if (!name || typeof name !== "string") {
    throw new Error("getOperationPathFromVaultKey requires name.");
  }
  return path.join(getOperationDirFromVaultKey({ vaultKey, group }), `${sanitizeForPath(name)}.json`);
}

function getManifestPathFromVaultKey({ vaultKey, operation }) {
  return getOperationPathFromVaultKey({ vaultKey, group: "selections", name: operation });
}

function getOperationPath(app, { group = "selections", name }) {
  return getOperationPathFromVaultKey({ vaultKey: getVaultKey(app), group, name });
}

function getManifestPath(app, operation) {
  return getManifestPathFromVaultKey({ vaultKey: getVaultKey(app), operation });
}

function readJsonFile(file, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return fallback;
    throw error;
  }
}

function writeJsonFile(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  return file;
}

function readManifest(app, operation) {
  return readJsonFile(getManifestPath(app, operation), null);
}

module.exports = {
  autoscribeHome,
  shortHash,
  getVaultKeyFromRoot,
  getVaultKey,
  getOperationDirFromVaultKey,
  getOperationPathFromVaultKey,
  getOperationPath,
  getManifestPathFromVaultKey,
  getManifestPath,
  readJsonFile,
  writeJsonFile,
  readManifest,
};
