"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { buildSlugPathMap } = require("./rg.js");
const { getVaultBasePath } = require("./query-runtime.js");

function normalizeCell(value) {
  return String(value ?? "")
    .replace(/\r/g, "")
    .trim();
}

function isSlug(value) {
  const text = normalizeCell(value);
  if (!text || /\s/.test(text) || text.includes("/") || text.includes("\\")) return false;
  return text.includes(".") && !text.startsWith(".") && !text.endsWith(".");
}

function isFilepath(value) {
  const text = normalizeCell(value);
  if (!text) return false;
  return text.includes("/") || text.includes("\\") || /\.md$/i.test(text);
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
  if (isFilepath(text)) return { type: "path", value: text };
  if (isSlug(text)) return { type: "slug", value: text };
  if (startsWithCapital(text)) return { type: "title", value: text };
  return { type: "hint", value: text };
}

function isHeaderRow(cells) {
  const labels = new Set(cells.map((cell) => normalizeCell(cell).toLowerCase()));
  return ["file name", "filename", "file", "title", "path", "filepath", "slug"]
    .some((label) => labels.has(label));
}

function parseTabDelimitedSelection(text) {
  const source = String(text ?? "").replace(/\r\n?/g, "\n").trim();
  if (!source) throw new Error("The clipboard is empty.");

  const rows = [];
  const sourceRows = source.split("\n");

  for (let sourceIndex = 0; sourceIndex < sourceRows.length; sourceIndex += 1) {
    const line = sourceRows[sourceIndex];
    if (!line.trim()) continue;
    const cells = line.split("\t");
    if (isHeaderRow(cells)) continue;

    const item = {
      index: rows.length + 1,
      source_row: sourceIndex + 1,
      title: "",
      path: "",
      slug: "",
      hints: [],
    };

    for (const rawCell of cells) {
      const match = classifyCell(rawCell);
      if (!match) continue;
      if (match.type === "hint") item.hints.push(match.value);
      else if (!item[match.type]) item[match.type] = match.value;
    }

    if (item.title || item.path || item.slug || item.hints.length) rows.push(item);
  }

  if (!rows.length) throw new Error("The clipboard contains no usable rows.");
  return rows;
}

function normalizeRelativePath(root, rawPath) {
  const text = normalizeCell(rawPath).replace(/\\/g, "/");
  if (!text) return "";
  const absolute = path.isAbsolute(text) ? path.resolve(text) : path.resolve(root, text);
  const relative = path.relative(root, absolute);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) return "";
  return relative.replace(/\\/g, "/");
}

function resolveClipboardRows(app, rows) {
  const root = getVaultBasePath(app);
  if (!root) throw new Error("Clipboard selection requires a filesystem-backed vault.");

  const { bySlug, duplicates } = buildSlugPathMap({ root });

  return rows.map((row) => {
    const item = { ...row, hints: Array.isArray(row.hints) ? [...row.hints] : [] };

    if (item.path) {
      const rel = normalizeRelativePath(root, item.path);
      if (rel && fs.existsSync(path.join(root, rel))) item.path = rel;
      else item.path = "";
    }

    const candidates = [item.slug, ...item.hints].filter(Boolean);
    if (!item.path) {
      for (const candidate of candidates) {
        if (duplicates.has(candidate)) {
          throw new Error(`Clipboard row ${item.source_row}: slug is duplicated in the vault: ${candidate}`);
        }
        const record = bySlug.get(candidate);
        if (!record) continue;
        item.slug = record.slug;
        item.path = record.path;
        break;
      }
    }

    delete item.hints;
    return item;
  });
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

async function readClipboardSelection(app) {
  const text = await readClipboardText();
  return resolveClipboardRows(app, parseTabDelimitedSelection(text));
}

module.exports = {
  classifyCell,
  isFilepath,
  isSlug,
  parseTabDelimitedSelection,
  readClipboardSelection,
  readClipboardText,
  resolveClipboardRows,
  startsWithCapital,
};
