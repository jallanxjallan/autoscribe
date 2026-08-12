"use strict";

const path = require("node:path");

// Control-package local resolver. This file deliberately does not know about
// cli/ or any top-level shared lib folder.
const CONTROL_LIB_ROOT = __dirname;
const CONTROL_SCRIPTS_ROOT = path.resolve(__dirname, "..");
const CONTROL_ROOT = path.resolve(CONTROL_SCRIPTS_ROOT, "..");

function assertRelativeName(name, functionName) {
  if (!name || typeof name !== "string") {
    throw new Error(`${functionName} requires a non-empty string`);
  }

  if (path.isAbsolute(name)) {
    throw new Error(`${functionName} expects a relative module name, not an absolute path: ${name}`);
  }

  const parts = name.split(/[\\/]+/).filter(Boolean);
  if (parts.some((part) => part === "..")) {
    throw new Error(`${functionName} does not accept parent-directory segments: ${name}`);
  }

  return parts;
}

function localLibPath(name) {
  return path.join(CONTROL_LIB_ROOT, ...assertRelativeName(name, "localLibPath"));
}

function controlScriptPath(name) {
  return path.join(CONTROL_SCRIPTS_ROOT, ...assertRelativeName(name, "controlScriptPath"));
}

function share(name) {
  return require(localLibPath(name));
}

function requireSharedLib(name) {
  return share(name);
}

function requireControlScript(name) {
  return require(controlScriptPath(name));
}

module.exports = {
  CONTROL_ROOT,
  CONTROL_SCRIPTS_ROOT,
  CONTROL_LIB_ROOT,
  localLibPath,
  controlScriptPath,
  share,
  requireSharedLib,
  requireControlScript,
};
