"use strict";

const { normalizeFolder } = require("./text.js");

function normalizeVaultPath(value) {
  return normalizeFolder(String(value || "").replace(/\\/g, "/"));
}

function isFolder(item) {
  return Boolean(item && Array.isArray(item.children));
}

function isMarkdownFile(item) {
  return Boolean(item && item.extension === "md");
}

function isControlPath(value, controlRoot = "_control") {
  const path = normalizeVaultPath(value);
  const root = normalizeVaultPath(controlRoot);
  return path === root || path.startsWith(`${root}/`);
}

async function ensureFolder(app, folderPath) {
  const normalized = normalizeVaultPath(folderPath);
  if (!normalized) return;

  const existing = app.vault.getAbstractFileByPath(normalized);
  if (isFolder(existing)) return;
  if (existing) throw new Error(`A file already occupies ${normalized}.`);

  let current = "";
  for (const part of normalized.split("/").filter(Boolean)) {
    current = current ? `${current}/${part}` : part;
    const item = app.vault.getAbstractFileByPath(current);
    if (isFolder(item)) continue;
    if (item) throw new Error(`A file already occupies ${current}.`);
    await app.vault.createFolder(current);
  }
}

function markdownFiles(app, { excludeControl = false, controlRoot = "_control" } = {}) {
  return app.vault.getMarkdownFiles().filter((file) =>
    !excludeControl || !isControlPath(file.path, controlRoot)
  );
}

module.exports = {
  normalizeVaultPath,
  isFolder,
  isMarkdownFile,
  isControlPath,
  ensureFolder,
  markdownFiles,
};
