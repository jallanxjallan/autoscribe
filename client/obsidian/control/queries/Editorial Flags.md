# Editorial Flags

````dataviewjs
const PREVIEW_LIMIT = 120;

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPath = app.workspace.getActiveFile()?.path || "";
const markerIndex = queryPath.indexOf("/queries/");

if (markerIndex === -1) {
  throw new Error(`Query is not inside a queries folder: ${queryPath}`);
}

const controlRoot = queryPath.slice(0, markerIndex);
const loadControl = (relativePath) => nodeRequire(
  pathMod.join(vaultBasePath, ...controlRoot.split("/").filter(Boolean), ...relativePath.split("/"))
);
const { createInternalLink } = loadControl("scripts/lib/internal-link.js");

function isExcludedFolder(filePath) {
  return filePath
    .split("/")
    .slice(0, -1)
    .some((part) => part.startsWith("_"));
}

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

function extractCallout(line) {
  const match = line.match(/^\s*>\s*\\?\[!([^\]]+)\](?:[+-])?\s*(.*)$/i);
  if (!match) return null;

  const type = normalizeType(match[1]);
  const text = truncateAtWord(match[2]) || `${type} callout`;
  return { type, text };
}

function extractHighlights(line) {
  return [...line.matchAll(/==(.+?)==/g)]
    .map((match) => match[1].trim())
    .filter(Boolean)
    .map((text) => {
      const aiMatch = text.match(/^\{\{ai:([^|}]+)\|([\s\S]+)\}\}$/i);
      if (aiMatch) {
        return {
          type: `AI · ${normalizeType(aiMatch[1])}`,
          text: truncateAtWord(aiMatch[2]),
        };
      }

      return { type: "Highlight", text: truncateAtWord(text) };
    });
}

function extractTk(line) {
  const match = /\*\*TK\s*([\s\S]*?)\*\*/i.exec(line);
  if (!match) return null;
  return { type: "TK", text: truncateAtWord(match[1]) || "TK" };
}

async function collectFlags() {
  const flags = [];

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

      const found = [];
      const callout = extractCallout(line);
      if (callout) found.push(callout);

      const tk = extractTk(line);
      if (tk) found.push(tk);

      found.push(...extractHighlights(line));

      for (const flag of found) {
        flags.push({
          ...flag,
          path: file.path,
          title,
          line: index + 1,
        });
      }
    }
  }

  return flags;
}

function compareText(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

function compareFlags(a, b) {
  return compareText(a.title, b.title) || a.line - b.line || compareText(a.text, b.text);
}

const flags = await collectFlags();
const grouped = new Map();

for (const flag of flags) {
  if (!grouped.has(flag.type)) grouped.set(flag.type, []);
  grouped.get(flag.type).push(flag);
}

if (!flags.length) {
  dv.paragraph("*No editorial flags found.*");
} else {
  const root = dv.container.createDiv({ cls: "editorial-flags" });
  const types = [...grouped.keys()].sort((a, b) => {
    if (a === "Defer" && b !== "Defer") return 1;
    if (b === "Defer" && a !== "Defer") return -1;
    return compareText(a, b);
  });

  for (const type of types) {
    const items = grouped.get(type).sort(compareFlags);
    if (!items.length) continue;

    const details = root.createEl("details");
    const summary = details.createEl("summary");
    summary.createEl("strong", { text: `${type} (${items.length})` });

    const table = details.createEl("table");
    const head = table.createEl("thead").createEl("tr");
    head.createEl("th", { text: "Note" });
    head.createEl("th", { text: "Flag" });

    const body = table.createEl("tbody");
    for (const item of items) {
      const row = body.createEl("tr");
      const noteCell = row.createEl("td");
      createInternalLink(noteCell, app, item.path, item.title);
      noteCell.createEl("small", { text: ` · line ${item.line}` });
      row.createEl("td", { text: item.text });
    }
  }
}
````
