```dataviewjs
const CONFIG = {
  contentsPrefix: "",
  tocPath: "Table of Contents.md",
  defaultComponent: "narrative",
  ungroupedHeading: "Ungrouped",
  alphabeticalHeading: "Alphabetical",

  slugPrefixes: ["cnt", "img"],
  excludePaths: [],

  tempRoot: "",
  debug: false
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
const runtime = createQueryRuntime({ app, queryTitle: "Slug Status query" });
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
  return CONFIG.excludePaths.some(prefix =>
    clean === normalizePath(prefix) ||
    clean.startsWith(`${normalizePath(prefix).replace(/\/+$/, "")}/`)
  );
}

function slugAllowed(slug) {
  const clean = asText(slug);
  if (!clean) return false;

  return CONFIG.slugPrefixes.some(prefix =>
    clean === prefix || clean.startsWith(`${prefix}.`) || clean.startsWith(`${prefix}-`)
  );
}

function pathAllowed(path) {
  const clean = normalizePath(path);
  return !isExcludedPath(clean);
}

function publicSluggedPageForPath(path) {
  const clean = normalizePath(path);
  if (!pathAllowed(clean)) return null;

  const page = dv.page(clean);
  if (!page || !slugAllowed(page.slug)) return null;

  return page;
}

function rowNameFor(page, fallback) {
  return asText(page?.title) || asText(fallback) || asText(page?.file?.name);
}

function statusRowFromPage(page, { heading, order }) {
  const path = normalizePath(page.file.path);
  const name = rowNameFor(page, page.file.name);

  return {
    id: asText(page.slug),
    selection_key: asText(page.slug),

    heading,
    order,

    path,
    name,
    title: name,
    slug: asText(page.slug),
    type: asText(page.type),
    status: asText(page.status),
    stage: asText(page.stage),
    process: asText(page.process),
    component: asText(page.component, CONFIG.defaultComponent)
  };
}

function allPublicSluggedPages() {
  return app.vault.getMarkdownFiles()
    .map(file => publicSluggedPageForPath(file.path))
    .filter(Boolean);
}

function alphaCompare(a, b) {
  return String(a.name || a.title || a.path).localeCompare(
    String(b.name || b.title || b.path),
    undefined,
    { sensitivity: "base" }
  );
}

function buildAlphabeticalRows({ heading = CONFIG.alphabeticalHeading } = {}) {
  return allPublicSluggedPages()
    .map((page, index) => statusRowFromPage(page, { heading, order: index }))
    .sort(alphaCompare)
    .map((row, index) => ({ ...row, order: index }));
}

function serializeStatusRow(row) {
  return {
    selection_key: row.slug,
    slug: row.slug,
    title: row.title || row.name,
    path: row.path,
    heading: row.heading,
    type: row.type,
    status: row.status,
    stage: row.stage,
    process: row.process,
    component: row.component
  };
}

function savedSelectionExtras({ rows }) {
  return {
    ordering: "alphabetical",
    slug_prefixes: CONFIG.slugPrefixes,
    exclude_paths: CONFIG.excludePaths,
    default_component: CONFIG.defaultComponent,
    displayed_count: rows.length
  };
}

async function saveSelectionManifest(api) {
  await api.saveDataviewSelection({
    operation: "slug-status",
    queryName: "Slug Status",
    namespace: "slug-status",
    selectionSource: "slug-status",
    selectionKind: "slug",
    selectionKey: "slug",
    serializeRow: serializeStatusRow,
    options: {
      slug_prefixes: CONFIG.slugPrefixes,
      exclude_paths: CONFIG.excludePaths,
      default_component: CONFIG.defaultComponent
    },
    savedSelectionExtras({ rows }) {
      return savedSelectionExtras({ rows });
    }
  });
}

function renderGroupedResults(parent, displayedRows, api) {
  const grouped = new Map();

  for (const row of displayedRows) {
    const heading = asText(row.heading, CONFIG.alphabeticalHeading);
    if (!grouped.has(heading)) grouped.set(heading, []);
    grouped.get(heading).push(row);
  }

  for (const [heading, groupRows] of grouped.entries()) {
    const section = parent.createDiv();
    section.style.marginBottom = "1.5em";

    const headingRow = section.createDiv();
    headingRow.style.display = "flex";
    headingRow.style.alignItems = "center";
    headingRow.style.gap = "0.6em";
    headingRow.style.marginBottom = "0.5em";

    const checkedCount = groupRows.filter(row => api.model.selectedKeys.has(row.slug)).length;

    const groupBox = headingRow.createEl("input", { type: "checkbox" });
    setTriState(groupBox, checkedCount, groupRows.length);
    groupBox.onchange = async () => {
      for (const row of groupRows) {
        if (groupBox.checked) api.model.selectedKeys.add(row.slug);
        else api.model.selectedKeys.delete(row.slug);
      }

      await api.saveCurrentState({ quiet: true, action: "selection" });
      api.render();
    };

    headingRow.createEl("strong", { text: heading });

    const countText = headingRow.createEl("span");
    countText.style.opacity = "0.75";
    countText.setText(`(${checkedCount}/${groupRows.length})`);

    const tableWrap = section.createDiv();
    tableWrap.style.overflowX = "auto";

    const table = tableWrap.createEl("table");
    table.classList.add("dataview", "table-view-table");
    table.style.width = "100%";

    const thead = table.createEl("thead");
    const headRow = thead.createEl("tr");
    ["", "Title", "Slug", "Status", "Stage"].forEach(text =>
      headRow.createEl("th", { text })
    );

    const tbody = table.createEl("tbody");

    for (const row of groupRows) {
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
      api.createInternalLink(noteCell, row.path, row.name);

      tr.createEl("td", { text: row.slug });
      tr.createEl("td", { text: row.status });
      tr.createEl("td", { text: row.stage });
    }
  }
}

const rows = buildAlphabeticalRows();

if (!rows.length) {
  dv.container.innerHTML = "";
  dv.paragraph("No Markdown files with frontmatter `slug` beginning `cnt` or `ins` were found.");
  return;
}

await renderSelectionQuery({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,

  title: "Slug Status",
  namespace: "slug-status",
  bridgeName: "__slugStatusSelection",

  vaultName,
  queryPath,
  stateVersion: 1,
  tempRoot: CONFIG.tempRoot,

  rows,
  columns: [],
  filterFields: [
    { key: "status", title: "Status" },
    { key: "stage", title: "Stage" },
  ],
  sortModes: [],
  defaultSortMode: "alphabetical",

  selectionKind: "slug",
  selectionKey: "slug",
  serializeRow: serializeStatusRow,
  savedSelectionExtras({ rows }) {
    return savedSelectionExtras({ rows });
  },

  emptyMessage: "No Markdown files with frontmatter `slug` beginning `cnt` or `ins` were found.",
  noMatchesMessage: "No matching slugged files.",

  summaryText({ displayedRows, selectedRows }) {
    return `${displayedRows.length} slugged file(s) displayed alphabetically · ${selectedRows.length} checked`;
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