const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { sanitizeForPath } = require("./text");

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

function getManifestPathFromVaultKey({ vaultKey, operation }) {
  if (!vaultKey || typeof vaultKey !== "string") {
    throw new Error("getManifestPathFromVaultKey requires vaultKey.");
  }
  if (!operation || typeof operation !== "string") {
    throw new Error("getManifestPathFromVaultKey requires operation.");
  }

  return path.join(
    autoscribeHome(),
    "obsidian",
    "vaults",
    vaultKey,
    "selections",
    `${sanitizeForPath(operation)}.json`
  );
}

module.exports = {
  autoscribeHome,
  shortHash,
  getVaultKeyFromRoot,
  getManifestPathFromVaultKey,
};
