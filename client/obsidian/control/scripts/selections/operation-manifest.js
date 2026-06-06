"use strict";

const {
  getVaultKey,
  getManifestPath,
  readManifest,
  writeManifest: writeOperationManifest,
} = require("../lib/operation-manifest");

function writeManifest(app, operation, manifest) {
  const result = writeOperationManifest(app, operation, manifest);
  return result.manifestPath;
}

module.exports = {
  getVaultKey,
  getManifestPath,
  readManifest,
  writeManifest,
};
