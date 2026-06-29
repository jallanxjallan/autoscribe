```dataviewjs
const CONFIG = {
  contentsPrefix: "contents/",
  tocPath: "Table of Contents.md",
  defaultComponent: "narrative",
  ungroupedHeading: "Ungrouped",
  alphabeticalHeading: "Alphabetical",

  slugPrefixes: [],
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
const runtime = createQueryRuntime({ app, queryTitle: "Content Status query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { setTriState } = loader.requireControl("scripts/lib/dom.js");

const {
  buildTocGroups,
  findUnlinkedContentFiles
} = loader.requireControl("scripts/lib/toc-index.js");

const {
  renderTocAuditSections
} = loader.requireControl("scripts/lib/toc-audit-ui.js");

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
  if (!CONFIG.slugPrefixes.length) return true;
  return CONFIG.slugPrefixes.some(prefix => clean.startsWith(prefix));
}

function pathAllowed(path) {
  const clean = normalizePath(path);
  if (isExcludedPath(clean)) return false;
  if (!CONFIG.contentsPrefix) return true;
  const prefix = normalizePath(CONFIG.contentsPrefix).replace(/\/+$/, "");
  return clean === prefix || clean.startsWith(`${prefix}/`);
}

function publicSluggedPageForPath(path) {
  const clean = normalizePath(path);
  if (!pathAllowed(clean)) return null;

  const page = dv.page(clean);
  if (!page || !slugAllowed(page.slug)) return null;

  return page;
}

function folderFromPath(path) {
  const parts = normalizePath(path).split("/");
  parts.pop();
  return parts.join("/") || "/";
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

function statusRowFromTocRow(tocRow, order) {
  const page = publicSluggedPageForPath(tocRow.path);
  if (!page) return null;

  return {
    ...statusRowFromPage(page, {
      heading: asText(tocRow.heading, CONFIG.ungroupedHeading),
      order
    }),

    toc_id: tocRow.id,
    toc_component: tocRow.component,
    component: asText(page.component, asText(tocRow.component, CONFIG.defaultComponent))
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

function buildAlphabeticalRows({ excludePaths = new Set(), heading = CONFIG.alphabeticalHeading } = {}) {
  return allPublicSluggedPages()
    .filter(page => !excludePaths.has(normalizePath(page.file.path)))
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

function savedSelectionExtras({ rows, tocFile, badTocLinks, unlinkedContentFiles, ordering }) {
  return {
    ordering,
    toc_path: CONFIG.tocPath,
    toc_exists: Boolean(tocFile),
    toc_link_issue_count: badTocLinks.length,
    unlinked_public_slugged_content_count: unlinkedContentFiles.length,
    options: {
      contents_prefix: CONFIG.contentsPrefix,
      slug_prefixes: CONFIG.slugPrefixes,
      exclude_paths: CONFIG.excludePaths,
      default_component: CONFIG.defaultComponent
    },
    displayed_count: rows.length
  };
}

async function saveSelectionManifest(api, context) {
  await api.saveDataviewSelection({
    operation: "content-status",
    queryName: "Content Status",
    namespace: "content-status",
    selectionSource: "content-status",
    selectionKind: "slug",
    selectionKey: "slug",
    serializeRow: serializeStatusRow,
    options: {
      contents_prefix: CONFIG.contentsPrefix,
      toc_path: CONFIG.tocPath,
      slug_prefixes: CONFIG.slugPrefixes,
      exclude_paths: CONFIG.excludePaths,
      default_component: CONFIG.defaultComponent
    },
    savedSelectionExtras({ rows }) {
      return savedSelectionExtras({ rows, ...context });
    }
  });
}

function renderGroupedResults(parent, displayedRows, api) {
  const grouped = new Map();

  for (const row of displayedRows) {
    const heading = asText(row.heading, CONFIG.ungroupedHeading);
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
    ["", "Title", "Status", "Stage"].forEach(text =>
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

      

      tr.createEl("td", { text: row.status });
      tr.createEl("td", { text: row.stage });


    }
  }
}

let tocFile = null;
let badTocLinks = [];
let unlinkedContentFiles = [];
let rows = [];
let ordering = "alphabetical";

const tocResult = await buildTocGroups({
  app,
  tocPath: CONFIG.tocPath,
  contentsPrefix: CONFIG.contentsPrefix,
  defaultComponent: CONFIG.defaultComponent,
  ungroupedHeading: CONFIG.ungroupedHeading
});

tocFile = tocResult.tocFile;
badTocLinks = tocResult.badTocLinks || [];

if (tocFile) {
  const linkedContentPaths = new Set(
    [...(tocResult.linkedContentPaths || [])].map(path => normalizePath(path))
  );

  unlinkedContentFiles = findUnlinkedContentFiles({
    app,
    linkedContentPaths,
    contentsPrefix: CONFIG.contentsPrefix
  }).filter(file => publicSluggedPageForPath(file.path));

  const tocRows = [];
  let order = 0;

  for (const group of tocResult.groups || []) {
    for (const item of group.items || []) {
      const row = statusRowFromTocRow(item, order++);
      if (row) tocRows.push(row);
    }
  }

  const unlinkedRows = unlinkedContentFiles
    .map(file => publicSluggedPageForPath(file.path))
    .filter(Boolean)
    .map((page, index) => statusRowFromPage(page, {
      heading: CONFIG.ungroupedHeading,
      order: tocRows.length + index
    }))
    .sort(alphaCompare)
    .map((row, index) => ({ ...row, order: tocRows.length + index }));

  rows = [...tocRows, ...unlinkedRows];
  ordering = "toc";
} else {
  rows = buildAlphabeticalRows();
}

if (!rows.length) {
  dv.container.innerHTML = "";
  dv.paragraph("No public Markdown files with frontmatter `slug` were found.");
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
  stateVersion: 4,
  tempRoot: CONFIG.tempRoot,

  rows,
  columns: [],
  filterFields: [
    { key: "status", title: "Status" },
    { key: "stage", title: "Stage" },
  ],
  sortModes: [],
  defaultSortMode: ordering,

  selectionKind: "slug",
  selectionKey: "slug",
  serializeRow: serializeStatusRow,
  savedSelectionExtras({ rows }) {
    return savedSelectionExtras({
      rows,
      tocFile,
      badTocLinks,
      unlinkedContentFiles,
      ordering
    });
  },

  emptyMessage: "No public Markdown files with frontmatter `slug` were found.",
  noMatchesMessage: "No matching public slugged files.",

  summaryText({ displayedRows, selectedRows }) {
    const visibleHeadingCount = new Set(displayedRows.map(row => row.heading)).size;
    const orderText = ordering === "toc" ? "TOC order" : "alphabetical order";
    return `${visibleHeadingCount} heading group(s) · ${displayedRows.length} public slugged file(s) displayed in ${orderText} · ${selectedRows.length} checked · ${badTocLinks.length} TOC link issue(s) · ${unlinkedContentFiles.length} unlinked public slugged content file(s)`;
  },

  renderSummaryExtras(parent, { api }) {
    if (!tocFile) {
      const note = parent.createEl("p");
      note.style.opacity = "0.75";
      note.setText(`No ${CONFIG.tocPath} found. Displaying public slugged content alphabetically.`);
      return;
    }

    renderTocAuditSections(parent, {
      tocFile,
      badTocLinks,
      unlinkedContentFiles
    }, api.createInternalLink);
  },

  renderActions(parent, api) {
    const saveButton = parent.createEl("button", { text: "Save selection manifest" });
    saveButton.onclick = async () => {
      await saveSelectionManifest(api, {
        tocFile,
        badTocLinks,
        unlinkedContentFiles,
        ordering
      });
    };
  },

  renderResults: renderGroupedResults,

  debug: CONFIG.debug
});
```