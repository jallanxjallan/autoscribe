"use strict";

const path = require("node:path");
const {
  getManifestPath,
  writeJsonFile,
} = require("../lib/operation-manifest.js");

function saveSelection(app, slug, selection) {
  if (!slug || typeof slug !== "string") throw new Error("saveSelection requires slug.");
  const file = getManifestPath(app, slug);
  writeJsonFile(file, selection);
  return file;
}

module.exports = { saveSelection };
