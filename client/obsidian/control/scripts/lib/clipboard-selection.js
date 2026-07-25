"use strict";

function normalizeCell(value) {
  return String(value ?? "")
    .replace(/\r/g, "")
    .trim();
}

function isSlug(value) {
  const text = normalizeCell(value);
  if (!text || /\s/.test(text)) return false;

  const parts = text.split(".");
  return parts.length === 3 && parts.every(Boolean);
}

function isFilepath(value) {
  const text = normalizeCell(value);
  if (!text) return false;

  const slash = text.indexOf("/");
  return slash > 0 && slash < text.length - 1;
}

function startsWithCapital(value) {
  const text = normalizeCell(value);
  if (!text) return false;

  const first = Array.from(text)[0];
  return first === first.toLocaleUpperCase() && first !== first.toLocaleLowerCase();
}

function classifyCell(value) {
  const text = normalizeCell(value);
  if (!text) return null;

  // Order matters: a capitalized filepath must remain a filepath.
  if (isFilepath(text)) return { type: "path", value: text };
  if (isSlug(text)) return { type: "slug", value: text };
  if (startsWithCapital(text)) return { type: "title", value: text };
  return null;
}

function parseTabDelimitedSelection(text) {
  const source = String(text ?? "").replace(/\r\n?/g, "\n").trim();
  if (!source) {
    throw new Error("The clipboard is empty.");
  }
  if (!source.includes("\t")) {
    throw new Error("The clipboard does not contain a tab-delimited list.");
  }

  const rows = [];
  const sourceRows = source.split("\n");

  for (let sourceIndex = 0; sourceIndex < sourceRows.length; sourceIndex += 1) {
    const line = sourceRows[sourceIndex];
    if (!line.trim()) continue;

    const item = {
      index: rows.length + 1,
      source_row: sourceIndex + 1,
      title: "",
      path: "",
      slug: "",
    };

    for (const rawCell of line.split("\t")) {
      const match = classifyCell(rawCell);
      if (!match) continue;
      if (!item[match.type]) item[match.type] = match.value;
    }

    if (item.title || item.path || item.slug) rows.push(item);
  }

  if (!rows.length) {
    throw new Error("The clipboard contains no recognizable titles, filepaths, or slugs.");
  }

  return rows;
}

async function readClipboardText() {
  const readText = globalThis.navigator?.clipboard?.readText;
  if (typeof readText !== "function") {
    throw new Error("Clipboard reading is not available in this Obsidian environment.");
  }

  try {
    return await readText.call(globalThis.navigator.clipboard);
  } catch (error) {
    const detail = error?.message ? `: ${error.message}` : "";
    throw new Error(`Could not read the clipboard${detail}`);
  }
}

async function readClipboardSelection() {
  const text = await readClipboardText();
  return parseTabDelimitedSelection(text);
}

module.exports = {
  classifyCell,
  isFilepath,
  isSlug,
  parseTabDelimitedSelection,
  readClipboardSelection,
  readClipboardText,
  startsWithCapital,
};
