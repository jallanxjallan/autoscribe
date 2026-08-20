"use strict";

const { loadConfig } = require("./config-loader");

function annotationConfig() { return loadConfig("annotations"); }
function vocabularyConfig() { return loadConfig("vocabulary"); }

function annotationTypes() {
  return Object.entries(annotationConfig().types || {})
    .map(([id, item]) => ({ id, ...item }))
    .sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
}

function inlineKeys() {
  return Object.entries(annotationConfig().keys || {}).map(([id, item]) => ({ id, ...item }));
}


function previewLimit() { return Number(annotationConfig().preview_limit || 120); }
function excludedFolderPrefix() { return String(loadConfig("paths").excluded_folder_prefix || "_"); }
function typeId(role) { return String(annotationConfig().roles?.[role] || role); }
function typeDef(role) {
  const id = typeId(role);
  return { id, ...(annotationConfig().types?.[id] || {}) };
}
function validKey(id) { return inlineKeys().some((item) => item.id === String(id || "").trim()); }

function asText(value, fallback = "") {
  if (value == null) return fallback;
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ");
  return String(value).trim() || fallback;
}

function truncateAtWord(text, limit = previewLimit()) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  const slice = normalized.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");
  return `${(lastSpace > 0 ? slice.slice(0, lastSpace) : slice.slice(0, limit - 1)).trimEnd()}…`;
}

function isExcludedFolder(filePath) {
  return filePath
    .split("/")
    .slice(0, -1)
    .some((part) => part.startsWith(excludedFolderPrefix()));
}

function extractInlines(line) {
  return [...line.matchAll(/\[==(.+?)==\]\{([A-Za-z][\w-]*)="((?:\\.|[^"\\])*)"\}/g)]
    .map((match) => {
      const selectedText = match[1].trim();
      const key = match[2];
      let message = match[3];

      try {
        message = JSON.parse(`"${message}"`);
      } catch {
        // Keep the raw value if a hand-written attribute is not JSON-escaped.
      }

      const prefix = message.match(/^(hm|ai):\s*(.+)$/i);
      if (!prefix) return null;

      return {
        annotation: typeId("inline"),
        type: String(typeDef("inline").label || typeId("inline")),
        key,
        source: prefix[1].toLowerCase(),
        message,
        selectedText,
        text: truncateAtWord(`${key}: ${message} — ${selectedText}`),
      };
    })
    .filter((item) => item && item.selectedText && item.message.trim());
}

function parseLine(line) {
  return extractInlines(line);
}

async function collectAnnotations(app) {
  const annotations = [];

  for (const file of app.vault.getMarkdownFiles()
    .filter((item) => !isExcludedFolder(item.path))
    .sort((a, b) => a.path.localeCompare(b.path))) {
    const frontmatter = app.metadataCache.getFileCache(file)?.frontmatter ?? {};
    const title = asText(frontmatter.title, file.basename);
    const lines = (await app.vault.cachedRead(file)).split(/\r?\n/);

    let inFrontmatter = lines[0]?.trim() === "---";
    let fenceMarker = null;

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();

      if (inFrontmatter) {
        if (index > 0 && trimmed === "---") inFrontmatter = false;
        continue;
      }

      if (fenceMarker) {
        if (trimmed.startsWith(fenceMarker)) fenceMarker = null;
        continue;
      }

      const openingFence = trimmed.match(/^(`{3,}|~{3,})/);
      if (openingFence) {
        fenceMarker = openingFence[1];
        continue;
      }

      for (const item of parseLine(line)) {
        annotations.push({
          ...item,
          path: file.path,
          title,
          line: index + 1,
        });
      }
    }
  }

  return annotations;
}

function orderedRange(from, to) {
  if (from.line < to.line || (from.line === to.line && from.ch <= to.ch)) return { from, to };
  return { from: to, to: from };
}

function selectionRange(editor) {
  if (!editor.somethingSelected()) return null;
  return orderedRange(editor.getCursor("from"), editor.getCursor("to"));
}

function annotationSpan(text, { key, message }) {
  const span = String(text || "");
  if (!span.trim()) throw new Error("Select text to annotate.");

  const attribute = String(key || "").trim();
  if (!validKey(attribute)) {
    throw new Error(`Unsupported annotation key: ${attribute}`);
  }

  const value = String(message || "").trim();
  if (!/^(hm|ai):\s*\S/i.test(value)) {
    throw new Error('Annotation messages must begin with "hm:" or "ai:".');
  }

  return `[==${span}==]{${attribute}=${JSON.stringify(value)}}`;
}

function inline(text, { key, message }) {
  return annotationSpan(text, { key, message });
}


module.exports = {
  get ANNOTATION_TYPES() { return annotationTypes(); },
  get INLINE_KEYS() { return inlineKeys(); },
  get STAGES() { return [...(vocabularyConfig().stage || [])]; },
  get STATUSES() { return [...(vocabularyConfig().status || [])]; },
  get PREVIEW_LIMIT() { return previewLimit(); },
  isExcludedFolder,
  extractInlines,
  parseLine,
  collectAnnotations,
  selectionRange,
  inline,
};
