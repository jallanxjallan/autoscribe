"use strict";

function getNodeRequire() {
  if (typeof require === "function") return require;
  if (typeof window !== "undefined" && typeof window.require === "function") {
    return window.require;
  }
  throw new Error("Node require is unavailable in this Obsidian context.");
}

module.exports = { getNodeRequire };
