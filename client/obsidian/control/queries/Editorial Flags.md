# Editorial Flags

````dataviewjs
const PREVIEW_LIMIT = 60;

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPathForBootstrap = app.workspace.getActiveFile().path;
const markerIndexForBootstrap = queryPathForBootstrap.indexOf("/queries/");

if (markerIndexForBootstrap === -1) {
  throw new Error(`Query is not inside a queries folder: ${queryPathForBootstrap}`);
}

const controlRootForBootstrap = queryPathForBootstrap.slice(0, markerIndexForBootstrap);
const runtimePath = pathMod.join(
  vaultBasePath,
  ...controlRootForBootstrap.split("/").filter(Boolean),
  "scripts",
  "lib",
  "query-runtime.js"
);

const { createQueryRuntime } = nodeRequire(runtimePath);
const runtime = createQueryRuntime({ app, queryTitle: "Editorial Flags query" });
const { loader, queryPath, vaultName } = runtime;
const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");

function isExcludedFolder(path) {
  return path
    .split("/")
    .slice(0, -1)
    .some(part => part.startsWith("_"));
}

function asText(value, fallback = "") {
  if (value == null) return fallback;
  if (Array.isArray(value)) return value.map(item => String(item)).join(", ");
  return String(value).trim() || fallback;
}

function truncateAtWord(text, limit = PREVIEW_LIMIT) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;

  const slice = normalized.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");
  return (lastSpace > 0 ? slice.slice(0, lastSpace) : normalized.slice(0, limit - 1)).trimEnd() + "…";
}

function extractCalloutFirstLine(line) {
  const match = line.match(/^\s*>\s*(\\?\[!.*)$/i);
  if (!match) return null;

  const text = match[1]
    .replace(/\\/g, "")
    .replace(/[\[\]]/g, " ")
    .replace(/!\s*/, "")
    .replace(/\s+/g, " ")
    .trim();

  return text ? truncateAtWord(text) : null;
}

function extractHighlights(line) {
  return [...line.matchAll(/==(.+?)==/g)]
    .map(match => match[1].trim())
    .filter(Boolean)
    .map(text => truncateAtWord(text));
}

function tkPreview(line) {
  // Capture everything between '**TK' and '**'
  const match = /\*\*TK([\s\S]*?)\*\*/i.exec(line);
  
  // If a match is found, return the captured text (trimmed of extra spaces)
  return match ? match[1].trim() : null;
}

function titleForFile(file, frontmatter) {
  return asText(frontmatter.title, file.basename);
}

async function buildRows() {
  const rows = [];

  for (const file of app.vault.getMarkdownFiles()
    .filter(file => !isExcludedFolder(file.path))
    .sort((a, b) => a.path.localeCompare(b.path))) {

    const cache = app.metadataCache.getFileCache(file);
    const frontmatter = cache?.frontmatter ?? {};
    const slug = asText(frontmatter.slug);
    if (!slug) continue;

    const text = await app.vault.cachedRead(file);
    const lines = text.split(/\r?\n/);
    const flags = [];

    let inFrontmatter = lines[0]?.trim() === "---";
    let inFence = false;

    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      const trimmed = line.trim();

      if (inFrontmatter) {
        if (index > 0 && trimmed === "---") inFrontmatter = false;
        continue;
      }

      if (/^(```|~~~)/.test(trimmed)) {
        inFence = !inFence;
        continue;
      }

      if (inFence) continue;

      const callout = extractCalloutFirstLine(line);
      if (callout) flags.push({ line: index + 1, type: "Callout", text: callout });

      const tk = tkPreview(line);
      if (tk) flags.push({ line: index + 1, type: "TK", text: tk });

      for (const highlight of extractHighlights(line)) {
        flags.push({ line: index + 1, type: "Highlight", text: highlight });
      }
    }

    if (!flags.length) continue;

    rows.push({
      id: slug,
      selection_key: slug,
      slug,
      path: file.path,
      title: titleForFile(file, frontmatter),
      type: [...new Set(flags.map(flag => flag.type))],
      flags,
    });
  }

  return rows;
}

function alphaCompare(a, b) {
  return String(a.title || a.path).localeCompare(
    String(b.title || b.path),
    undefined,
    { sensitivity: "base" }
  );
}

function renderResults(parent, displayedRows, api) {
  const rows = [...displayedRows].sort(alphaCompare);
  const table = parent.createEl("table");
  const head = table.createEl("thead").createEl("tr");

  for (const title of ["", "Note", "Type", "Text"]) {
    head.createEl("th", { text: title });
  }

  const body = table.createEl("tbody");

  for (const row of rows) {
    row.flags.forEach((flag, index) => {
      const tr = body.createEl("tr");

      if (index === 0) {
        const selectCell = tr.createEl("td");
        selectCell.rowSpan = row.flags.length;

        const checkbox = selectCell.createEl("input", { type: "checkbox" });
        checkbox.checked = api.model.selectedKeys.has(row.slug);
        checkbox.onchange = async () => {
          if (checkbox.checked) api.model.selectedKeys.add(row.slug);
          else api.model.selectedKeys.delete(row.slug);
          await api.saveCurrentState({ quiet: true, action: "selection" });
          api.render();
        };

        const noteCell = tr.createEl("td");
        noteCell.rowSpan = row.flags.length;
        api.createInternalLink(noteCell, row.path, row.title);
      }

      tr.createEl("td", { text: flag.type });
      tr.createEl("td", { text: flag.text });
    });
  }
}

const rows = await buildRows();

await renderSelectionQuery({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,

  title: "Editorial Flags",
  namespace: "editorial-flags",
  bridgeName: "__editorialFlagsSelection",

  vaultName,
  queryPath,
  stateVersion: 1,

  rows,
  columns: [],

  filterFields: [
    { key: "type", title: "Type" },
  ],

  sortModes: [
    ["title-asc", "Title A–Z"],
    ["title-desc", "Title Z–A"],
  ],
  defaultSortMode: "title-asc",
  sortRows(items, mode) {
    return [...items].sort(mode === "title-desc" ? (a, b) => alphaCompare(b, a) : alphaCompare);
  },

  selectionKind: "slug",
  selectionKey: "slug",
  serializeRow(row) {
    return {
      selection_key: row.slug,
      slug: row.slug,
      title: row.title,
      path: row.path,
    };
  },

  emptyMessage: "No editorial flags found.",
  noMatchesMessage: "No matching editorial flags.",
  summaryText({ displayedRows, selectedRows }) {
    const flagCount = displayedRows.reduce((total, row) => total + row.flags.length, 0);
    return `${flagCount} editorial flag${flagCount === 1 ? "" : "s"} in ${displayedRows.length} file(s) · ${selectedRows.length} checked`;
  },

  renderResults,
});
````
