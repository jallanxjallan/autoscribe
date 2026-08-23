"use strict";

function createControlRuntime(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const loaderPath = path.join(base, "_control", "scripts", "lib", "control-loader.js");
  try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
  const { createControlLoader } = nodeRequire(loaderPath);
  return createControlLoader({ app, controlRoot: "_control" });
}

function getActiveMarkdownFile(app) {
  const file = app?.workspace?.getActiveFile();
  if (!file || file.extension !== "md") {
    throw new Error("The active file is not a Markdown file.");
  }
  return file;
}

function getSlug(app, file) {
  const cache = app.metadataCache.getFileCache(file);
  const slug = String(cache?.frontmatter?.slug ?? "").trim();
  if (!slug) throw new Error(`The active file is missing a slug: ${file.path}`);
  return slug;
}

function normalizeClipboardText(text) {
  return String(text ?? "").replace(/\r\n?/g, "\n").trim();
}

async function readClipboardText() {
  const clipboard = globalThis.navigator?.clipboard;
  if (typeof clipboard?.readText !== "function") {
    throw new Error("Clipboard reading is not available in this Obsidian environment.");
  }
  return clipboard.readText();
}

async function writeClipboardText(text) {
  const clipboard = globalThis.navigator?.clipboard;
  if (typeof clipboard?.writeText !== "function") {
    throw new Error("Clipboard writing is not available in this Obsidian environment.");
  }
  await clipboard.writeText(text);
}

module.exports = async function addActiveFileToClipboard(params = {}) {
  const app = params.app ?? globalThis.app;
  if (!app) throw new Error("Obsidian app instance is unavailable.");

  const loader = createControlRuntime(app);
  const { readClipboardSelection } = loader.requireControl("scripts/lib/clipboard-selection.js");
  const { notify } = loader.requireControl("scripts/lib/notify.js");
  if (typeof readClipboardSelection !== "function") {
    throw new Error("clipboard-selection.js does not export readClipboardSelection().");
  }

  const file = getActiveMarkdownFile(app);
  const slug = getSlug(app, file);
  const filename = file.name;
  const newLine = [slug, filename, file.path].join("\t");

  notify("Adding active file to clipboard…");

  let existingText = "";
  try {
    const rawClipboardText = await readClipboardText();
    const rows = await readClipboardSelection(app);
    const nonBlankLines = normalizeClipboardText(rawClipboardText)
      .split("\n")
      .filter((line) => line.trim());
    const allRowsResolved =
      rows.length > 0 &&
      rows.length === nonBlankLines.length &&
      rows.every((row) => row.path);
    if (allRowsResolved) existingText = normalizeClipboardText(rawClipboardText);
  } catch {
    existingText = "";
  }

  const output = existingText ? `${existingText}\n${newLine}` : newLine;
  await writeClipboardText(output);
  notify(`Added ${filename} to clipboard selection.`);
};
