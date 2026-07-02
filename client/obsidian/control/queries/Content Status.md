```dataviewjs
const CONFIG = {
  tempRoot: "",
  debug: false,

  defaultClass: "—",
  defaultStatus: "—",
  defaultStage: "—",
  defaultSlugPrefix: "—",

  excludePaths: [
    ".obsidian",
    ".trash",
    ".autoscribe",
  ],
};

const nodeRequire =
  typeof require === "function"
    ? require
    : window.require;

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
const runtime = createQueryRuntime({ app, queryTitle: "Content Status query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { setTriState } = loader.requireControl("scripts/lib/dom.js");

function asText(value, fallback = "") {
  if (value == null) return fallback;
  if (Array.isArray(value)) return value.map(v => String(v)).join(", ");
  const text = String(value).trim();
  return text || fallback;
}

function normalizePath(path) {
  return String(path || "").replace(/^\/+/, "");
}

function isExcludedPath(path) {
  const clean = normalizePath(path);

  if (isUnderscoreFolder(clean)) return true;

  return CONFIG.excludePaths.some(prefix => {
    const cleanPrefix = normalizePath(prefix).replace(/\/+$/, "");
    return clean === cleanPrefix || clean.startsWith(`${cleanPrefix}/`);
  });
}

function slugPrefix(slug) {
  const clean = asText(slug);
  if (!clean) return CONFIG.defaultSlugPrefix;

  const dotPrefix = clean.split(".")[0]?.trim();
  const dashPrefix = clean.split("-")[0]?.trim();

  if (dotPrefix && dotPrefix !== clean) return dotPrefix;
  if (dashPrefix && dashPrefix !== clean) return dashPrefix;

  return clean;
}

function titleForPage(page) {
  return (
    asText(page.title) ||
    asText(page.file?.name) ||
    asText(page.file?.path)
  );
}

function sluggedPageForPath(path) {
  const clean = normalizePath(path);
  if (isExcludedPath(clean)) return null;

  const page = dv.page(clean);
  if (!page) return null;

  const slug = asText(page.slug);
  if (!slug) return null;

  return page;
}

function allSluggedPages() {
  return app.vault.getMarkdownFiles()
    .map(file => sluggedPageForPath(file.path))
    .filter(Boolean);
}

function isUnderscoreFolder(path) {
  return normalizePath(path)
    .split("/")
    .some(part => part.startsWith("_"));
}

function statusRowFromPage(page) {
  const path = normalizePath(page.file.path);
  const slug = asText(page.slug);
  const title = titleForPage(page);
  const modifiedMillis = page.file?.mtime?.toMillis?.() ?? page.file?.mtime ?? 0;

  return {
    id: slug,
    selection_key: slug,

    path,
    name: title,
    title,
    slug,

    slug_prefix: slugPrefix(slug),

    class: asText(page.class, CONFIG.defaultClass),
    status: asText(page.status, CONFIG.defaultStatus),
    stage: asText(page.stage, CONFIG.defaultStage),
    process: asText(page.process),

    modified: modifiedMillis,
    modified_display: modifiedMillis
      ? window.moment(modifiedMillis).format("YYYY-MM-DD HH:mm")
      : "",
  };
}

function alphaCompare(a, b) {
  return String(a.title || a.name || a.path).localeCompare(
    String(b.title || b.name || b.path),
    undefined,
    { sensitivity: "base" }
  );
}

function buildRows() {
  return allSluggedPages().map(statusRowFromPage);
}

function serializeStatusRow(row) {
  return {
    selection_key: row.slug,
    slug: row.slug,
    slug_prefix: row.slug_prefix,
    title: row.title,
    path: row.path,
    class: row.class,
    status: row.status,
    stage: row.stage,
    process: row.process,
    modified: row.modified_display,
  };
}

function savedSelectionExtras({ rows }) {
  return {
    ordering: "content-status",
    displayed_count: rows.length,
    filters: ["class", "status", "stage", "slug_prefix"],
    sort_modes: ["title", "modified"],
  };
}

function sortRows(rows, mode) {
  const copy = [...rows];

  if (mode === "title-desc") {
    return copy.sort((a, b) => alphaCompare(b, a));
  }

  if (mode === "modified-desc") {
    return copy.sort((a, b) => Number(b.modified || 0) - Number(a.modified || 0));
  }

  if (mode === "modified-asc") {
    return copy.sort((a, b) => Number(a.modified || 0) - Number(b.modified || 0));
  }

  return copy.sort(alphaCompare);
}

function renderGroupedResults(parent, displayedRows, api) {
  const sortedRows = sortRows(displayedRows, api.model.sortMode || "title-asc");

  const section = parent.createDiv();
  section.style.marginBottom = "1.5em";

  const headingRow = section.createDiv();
  headingRow.style.display = "flex";
  headingRow.style.alignItems = "center";
  headingRow.style.gap = "0.6em";
  headingRow.style.marginBottom = "0.5em";

  const checkedCount = sortedRows.filter(row => api.model.selectedKeys.has(row.slug)).length;

  const groupBox = headingRow.createEl("input", { type: "checkbox" });
  setTriState(groupBox, checkedCount, sortedRows.length);
  groupBox.onchange = async () => {
    for (const row of sortedRows) {
      if (groupBox.checked) api.model.selectedKeys.add(row.slug);
      else api.model.selectedKeys.delete(row.slug);
    }

    await api.saveCurrentState({ quiet: true, action: "selection" });
    api.render();
  };

  headingRow.createEl("strong", { text: "Content Status" });

  const countText = headingRow.createEl("span");
  countText.style.opacity = "0.75";
  countText.setText(`(${checkedCount}/${sortedRows.length})`);

  const tableWrap = section.createDiv();
  tableWrap.style.overflowX = "auto";

  const table = tableWrap.createEl("table");
  table.classList.add("dataview", "table-view-table");
  table.style.width = "100%";

  const thead = table.createEl("thead");
  const headRow = thead.createEl("tr");

  [
    "",
    "Title",
    "Slug",
    "Prefix",
    "Class",
    "Status",
    "Stage",
    "Modified",
  ].forEach(text => headRow.createEl("th", { text }));

  const tbody = table.createEl("tbody");

  for (const row of sortedRows) {
    const tr = tbody.createEl("tr");

    const selectCell = tr.createEl("td");
    const itemBox = selectCell.createEl("input", { type: "checkbox" });
    itemBox.checked = api.model.selectedKeys.has(row.slug);
    itemBox.onchange = async () => {
      if (itemBox.checked) api.model.selectedKeys.add(row.slug);
      else api.model.selectedKeys.delete(row.slug);

      await api.saveCurrentState({ quiet: true, action: "selection" });
      api.render();
    };

    const noteCell = tr.createEl("td");
    api.createInternalLink(noteCell, row.path, row.title);

    tr.createEl("td", { text: row.slug });
    tr.createEl("td", { text: row.slug_prefix });
    tr.createEl("td", { text: row.class });
    tr.createEl("td", { text: row.status });
    tr.createEl("td", { text: row.stage });
    tr.createEl("td", { text: row.modified_display });
  }
}

async function saveSelectionManifest(api) {
  await api.saveDataviewSelection({
    operation: "content-status",
    queryName: "Content Status",
    namespace: "content-status",
    selectionSource: "content-status",
    selectionKind: "slug",
    selectionKey: "slug",
    serializeRow: serializeStatusRow,
    options: {
      filters: ["class", "status", "stage", "slug_prefix"],
      sort_modes: ["title", "modified"],
    },
    savedSelectionExtras({ rows }) {
      return savedSelectionExtras({ rows });
    }
  });
}

const rows = buildRows();

if (!rows.length) {
  dv.container.innerHTML = "";
  dv.paragraph("No Markdown files with frontmatter `slug` were found.");
  return;
}

await renderSelectionQuery({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,

  title: "Content Status",
  namespace: "content-status",
  bridgeName: "__contentStatusSelection",

  vaultName,
  queryPath,
  stateVersion: 1,
  tempRoot: CONFIG.tempRoot,

  rows,
  columns: [],

  filterFields: [
    { key: "class", title: "Class" },
    { key: "status", title: "Status" },
    { key: "stage", title: "Stage" },
    { key: "slug_prefix", title: "Slug Prefix" },
  ],

  sortModes: [
    ["title-asc", "Title A–Z"],
    ["title-desc", "Title Z–A"],
    ["modified-desc", "Modified newest"],
    ["modified-asc", "Modified oldest"],
  ],

  defaultSortMode: "title-asc",

  selectionKind: "slug",
  selectionKey: "slug",
  serializeRow: serializeStatusRow,
  savedSelectionExtras({ rows }) {
    return savedSelectionExtras({ rows });
  },

  emptyMessage: "No Markdown files with frontmatter `slug` were found.",
  noMatchesMessage: "No matching slugged files.",

  summaryText({ displayedRows, selectedRows }) {
    return `${displayedRows.length} slugged file(s) displayed · ${selectedRows.length} checked`;
  },

  renderActions(parent, api) {
    const saveButton = parent.createEl("button", { text: "Save selection manifest" });
    saveButton.onclick = async () => {
      await saveSelectionManifest(api);
    };
  },

  renderResults: renderGroupedResults,

  debug: CONFIG.debug
});
```

