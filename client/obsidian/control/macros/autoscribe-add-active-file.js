"use strict";

const fs = require("node:fs");
const path = require("node:path");

function getVaultRoot(app) {
  const adapter = app?.vault?.adapter;

  const root =
    typeof adapter?.getBasePath === "function"
      ? adapter.getBasePath()
      : adapter?.basePath;

  if (!root) {
    throw new Error("Could not determine the vault filesystem path.");
  }

  return path.resolve(root);
}

function loadClipboardSelectionLibrary(app) {
  const vaultRoot = getVaultRoot(app);

  const candidates = [
    path.join(vaultRoot, "_control", "lib", "clipboard-selection.js"),
    path.join(
      vaultRoot,
      "_control",
      "scripts",
      "lib",
      "clipboard-selection.js"
    ),
    path.join(vaultRoot, "scripts", "lib", "clipboard-selection.js"),
  ];

  const libraryPath = candidates.find((candidate) =>
    fs.existsSync(candidate)
  );

  if (!libraryPath) {
    throw new Error(
      [
        "Could not locate clipboard-selection.js.",
        "Checked:",
        ...candidates.map((candidate) => `- ${candidate}`),
      ].join("\n")
    );
  }

  return require(libraryPath);
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

  if (!slug) {
    throw new Error(`The active file is missing a slug: ${file.path}`);
  }

  return slug;
}

function normalizeClipboardText(text) {
  return String(text ?? "")
    .replace(/\r\n?/g, "\n")
    .trim();
}

async function readClipboardText() {
  const clipboard = globalThis.navigator?.clipboard;

  if (typeof clipboard?.readText !== "function") {
    throw new Error(
      "Clipboard reading is not available in this Obsidian environment."
    );
  }

  return clipboard.readText();
}

async function writeClipboardText(text) {
  const clipboard = globalThis.navigator?.clipboard;

  if (typeof clipboard?.writeText !== "function") {
    throw new Error(
      "Clipboard writing is not available in this Obsidian environment."
    );
  }

  await clipboard.writeText(text);
}

module.exports = async function addActiveFileToClipboard(params = {}) {
  const app = params.app ?? globalThis.app;

  if (!app) {
    throw new Error("Obsidian app instance is unavailable.");
  }

  const { readClipboardSelection } =
    loadClipboardSelectionLibrary(app);

  if (typeof readClipboardSelection !== "function") {
    throw new Error(
      "clipboard-selection.js does not export readClipboardSelection()."
    );
  }

  const file = getActiveMarkdownFile(app);
  const slug = getSlug(app, file);
  const filename = file.name;

  const systemPath = path.join(
    getVaultRoot(app),
    file.path
  );

  const newLine = [
    slug,
    filename,
    systemPath,
  ].join("\t");

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

  if (allRowsResolved) {
    existingText = normalizeClipboardText(rawClipboardText);
  }
} catch {
  existingText = "";
}

const output = existingText
  ? `${existingText}\n${newLine}`
  : newLine;

await writeClipboardText(output)
};
