"use strict";

const ANNOTATION_TYPES = Object.freeze([
  { id: "block", label: "Block", description: "Callout on the current paragraph" },
  { id: "inline", label: "Inline", description: "Highlight the selected text" },
  { id: "directive", label: "Directive", description: "Fenced instruction" },
]);

const INLINE_KEYS = Object.freeze([
  { id: "comment", label: "Comment" },
  { id: "query", label: "Query" },
  { id: "rewrite", label: "Rewrite" },
  { id: "verify", label: "Verify" },
  { id: "defer", label: "Defer" },
]);

const PREVIEW_LIMIT = 120;

function asText(value, fallback = "") {
  if (value == null) return fallback;
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ");
  return String(value).trim() || fallback;
}

function truncateAtWord(text, limit = PREVIEW_LIMIT) {
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
    .some((part) => part.startsWith("_"));
}

function extractBlock(line) {
  const match = line.match(/^\s*>\s*\\?\[!block\](?:[+-])?\s+(.+)$/i);
  if (!match) return null;
  return {
    annotation: "block",
    type: "Block",
    text: truncateAtWord(match[1]),
  };
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

      return {
        annotation: "inline",
        type: "Inline",
        key,
        message,
        selectedText,
        text: truncateAtWord(`${key}: ${message} — ${selectedText}`),
      };
    })
    .filter((item) => item.selectedText && item.message.trim());
}

function parseLine(line) {
  const found = [];
  const block = extractBlock(line);
  if (block) found.push(block);
  found.push(...extractInlines(line));
  return found;
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
    let fence = null;

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();

      if (inFrontmatter) {
        if (index > 0 && trimmed === "---") inFrontmatter = false;
        continue;
      }

      if (fence) {
        if (trimmed.startsWith(fence.marker)) {
          if (fence.directive) {
            annotations.push({
              annotation: "directive",
              type: "Directive",
              text: truncateAtWord(fence.lines.join("\n")) || "Empty directive",
              path: file.path,
              title,
              line: fence.line,
            });
          }
          fence = null;
        } else if (fence.directive) {
          fence.lines.push(line);
        }
        continue;
      }

      const openingFence = trimmed.match(/^(`{3,}|~{3,})\s*([^\s`]*)/);
      if (openingFence) {
        fence = {
          marker: openingFence[1],
          directive: openingFence[2].toLowerCase() === "directive",
          lines: [],
          line: index + 1,
        };
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

function paragraphRange(editor) {
  const cursor = editor.getCursor();
  let start = cursor?.line ?? 0;
  let end = start;

  while (start > 0 && editor.getLine(start - 1).trim()) start -= 1;
  while (end < editor.lineCount() - 1 && editor.getLine(end + 1).trim()) end += 1;

  return {
    from: { line: start, ch: 0 },
    to: { line: end, ch: editor.getLine(end).length },
  };
}

function quoteLines(text) {
  return String(text).split("\n").map((line) => `> ${line}`.trimEnd()).join("\n");
}

function block(text, message) {
  const firstLine = String(message || "").trim();
  if (!firstLine) throw new Error("A block annotation message is required.");

  return [
    `> [!block] ${firstLine}`,
    quoteLines(text),
  ].filter(Boolean).join("\n");
}

function inline(text, { key, message }) {
  const span = String(text || "");
  if (!span.trim()) throw new Error("Select the text to annotate inline.");

  const attribute = String(key || "").trim();
  if (!INLINE_KEYS.some((item) => item.id === attribute)) {
    throw new Error(`Unsupported inline key: ${attribute}`);
  }

  const value = String(message || "").trim();
  if (!value) throw new Error("An inline annotation message is required.");

  return `[==${span}==]{${attribute}=${JSON.stringify(value)}}`;
}

function directive(instruction) {
  const message = String(instruction || "").trim();
  if (!message) throw new Error("A directive instruction is required.");
  return `\`\`\`directive\n${message}\n\`\`\``;
}

module.exports = {
  ANNOTATION_TYPES,
  INLINE_KEYS,
  PREVIEW_LIMIT,
  isExcludedFolder,
  extractBlock,
  extractInlines,
  parseLine,
  collectAnnotations,
  selectionRange,
  paragraphRange,
  block,
  inline,
  directive,
};
