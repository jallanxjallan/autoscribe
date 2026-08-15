"use strict";

const ANNOTATION_TYPES = Object.freeze([
  { id: "callout", label: "Callout", description: "Obsidian callout: > [!Type] Summary" },
  { id: "highlight", label: "Highlight", description: "Markdown highlight: ==text==" },
  { id: "ai-highlight", label: "AI Highlight", description: "Typed highlight: =={{ai:type|text}}==" },
  { id: "tk", label: "TK", description: "TK marker: **TK ...**" },
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

function normalizeType(value) {
  return String(value || "")
    .trim()
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isExcludedFolder(filePath) {
  return filePath
    .split("/")
    .slice(0, -1)
    .some((part) => part.startsWith("_"));
}

function extractCallout(line) {
  const match = line.match(/^\s*>\s*\\?\[!([^\]]+)\](?:[+-])?\s*(.*)$/i);
  if (!match) return null;
  const type = normalizeType(match[1]);
  return {
    annotation: "callout",
    type,
    text: truncateAtWord(match[2]) || `${type} callout`,
  };
}

function extractHighlights(line) {
  return [...line.matchAll(/==(.+?)==/g)]
    .map((match) => match[1].trim())
    .filter(Boolean)
    .map((text) => {
      const aiMatch = text.match(/^\{\{ai:([^|}]+)\|([\s\S]+)\}\}$/i);
      if (aiMatch) {
        return {
          annotation: "ai-highlight",
          type: `AI · ${normalizeType(aiMatch[1])}`,
          aiType: normalizeType(aiMatch[1]),
          text: truncateAtWord(aiMatch[2]),
        };
      }
      return {
        annotation: "highlight",
        type: "Highlight",
        text: truncateAtWord(text),
      };
    });
}

function extractTk(line) {
  const match = /\*\*TK\s*([\s\S]*?)\*\*/i.exec(line);
  if (!match) return null;
  return {
    annotation: "tk",
    type: "TK",
    text: truncateAtWord(match[1]) || "TK",
  };
}

function parseLine(line) {
  const found = [];
  const callout = extractCallout(line);
  if (callout) found.push(callout);
  const tk = extractTk(line);
  if (tk) found.push(tk);
  found.push(...extractHighlights(line));
  return found;
}

async function collectAnnotations(app) {
  const annotations = [];

  for (const file of app.vault.getMarkdownFiles()
    .filter((item) => !isExcludedFolder(item.path))
    .sort((a, b) => a.path.localeCompare(b.path))) {

    const frontmatter = app.metadataCache.getFileCache(file)?.frontmatter ?? {};
    const title = asText(frontmatter.title, file.basename);
    const text = await app.vault.cachedRead(file);
    const lines = text.split(/\r?\n/);

    let inFrontmatter = lines[0]?.trim() === "---";
    let fenceMarker = null;

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();

      if (inFrontmatter) {
        if (index > 0 && trimmed === "---") inFrontmatter = false;
        continue;
      }

      const fence = trimmed.match(/^(```+|~~~+)/)?.[1] || null;
      if (fence) {
        if (!fenceMarker) fenceMarker = fence[0];
        else if (fence[0] === fenceMarker) fenceMarker = null;
        continue;
      }
      if (fenceMarker) continue;

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

function paragraphRange(editor) {
  const cursor = editor.getCursor();
  let start = cursor.line;
  let end = cursor.line;
  while (start > 0 && editor.getLine(start - 1).trim()) start -= 1;
  while (end < editor.lineCount() - 1 && editor.getLine(end + 1).trim()) end += 1;
  return {
    from: { line: start, ch: 0 },
    to: { line: end, ch: editor.getLine(end).length },
  };
}

function targetRange(editor) {
  if (editor.somethingSelected()) return orderedRange(editor.getCursor("from"), editor.getCursor("to"));
  return paragraphRange(editor);
}

function quoteLines(text) {
  return String(text).split("\n").map((line) => `> ${line}`.trimEnd()).join("\n");
}

function callout(text, { type, summary = "", note = "" }) {
  const calloutType = String(type || "").trim();
  if (!calloutType) throw new Error("Callout type is required.");

  const parts = [
    `> [!${calloutType}]${summary.trim() ? ` ${summary.trim()}` : ""}`,
  ];
  if (note.trim()) parts.push(quoteLines(note.trim()));
  if (text) parts.push(quoteLines(text));
  return parts.join("\n");
}

function highlight(text, span = "") {
  const needle = span.trim();
  if (!needle) return `==${text}==`;
  const index = text.indexOf(needle);
  if (index < 0) throw new Error("The requested highlight span was not found in the target text.");
  return `${text.slice(0, index)}==${needle}==${text.slice(index + needle.length)}`;
}

function aiHighlight(text, { type, span = "" }) {
  const aiType = String(type || "").trim();
  if (!aiType) throw new Error("AI highlight type is required.");

  const needle = span.trim();
  if (!needle) return `=={{ai:${aiType}|${text}}}==`;

  const index = text.indexOf(needle);
  if (index < 0) throw new Error("The requested highlight span was not found in the target text.");
  return `${text.slice(0, index)}=={{ai:${aiType}|${needle}}}==${text.slice(index + needle.length)}`;
}

function tk(text, note = "") {
  const detail = String(note || "").trim();
  return `**TK${detail ? ` ${detail}` : ""}**\n${text}`;
}

module.exports = {
  ANNOTATION_TYPES,
  PREVIEW_LIMIT,
  normalizeType,
  isExcludedFolder,
  extractCallout,
  extractHighlights,
  extractTk,
  parseLine,
  collectAnnotations,
  targetRange,
  callout,
  highlight,
  aiHighlight,
  tk,
};
