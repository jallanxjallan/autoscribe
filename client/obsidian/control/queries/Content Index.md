```dataviewjs
const CONFIG = {
  contentsPrefix: "contents/",
  tocPath: "Table of Contents.md",
  defaultComponent: "narrative",
  ungroupedHeading: "Ungrouped",
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
const runtime = createQueryRuntime({ app, queryTitle: "Content Index query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { setTriState } = loader.requireControl("scripts/lib/dom.js");
const { getManifestPath, writeJsonFile } = loader.requireControl("scripts/lib/operation-manifest.js");

const {
  buildTocGroups,
  findUnlinkedContentFiles,
  serializeTocRow,
  tocSavedSelectionExtras
} = loader.requireControl("scripts/lib/toc-index.js");

const {
  renderMissingToc,
  renderTocAuditSections
} = loader.requireControl("scripts/lib/toc-audit-ui.js");

function createObsidianLink(parent, path, text) {
  const link = parent.createEl("a", { text });
  link.classList.add("internal-link");
  link.setAttribute("href", path);
  link.setAttribute("data-href", path);
  link.addEventListener("click", event => {
    event.preventDefault();
    app.workspace.openLinkText(path, "", false);
  });
}

function renderEmptyWithAudit({ tocFile, badTocLinks, unlinkedContentFiles }) {
  const root = dv.container;
  root.innerHTML = "";

  const block = root.createDiv();
  block.style.padding = "1em";
  block.style.border = "1px solid var(--background-modifier-border)";
  block.style.borderRadius = "8px";
  block.style.background = "var(--background-secondary)";
  block.createEl("h3", { text: "No public slugged TOC entries found" });
  block.createEl("p", {
    text: `The TOC exists at ${CONFIG.tocPath}, but no TOC links resolved to public slugged Markdown files under ${CONFIG.contentsPrefix}.`
  });

  renderTocAuditSections(root, {
    tocFile,
    badTocLinks,
    unlinkedContentFiles
  }, createObsidianLink);
}

function renderGroupedResults(parent, displayedRows, api) {
  const grouped = new Map();

  for (const row of displayedRows) {
    if (!grouped.has(row.heading)) grouped.set(row.heading, []);
    grouped.get(row.heading).push(row);
  }

  for (const [heading, groupRows] of grouped.entries()) {
    const section = parent.createDiv();
    section.style.marginBottom = "1.5em";

    const headingRow = section.createDiv();
    headingRow.style.display = "flex";
    headingRow.style.alignItems = "center";
    headingRow.style.gap = "0.6em";
    headingRow.style.marginBottom = "0.5em";

    const checkedCount = groupRows.filter(row => api.model.selectedKeys.has(row.id)).length;

    const groupBox = headingRow.createEl("input", { type: "checkbox" });
    setTriState(groupBox, checkedCount, groupRows.length);
    groupBox.onchange = async () => {
      for (const row of groupRows) {
        if (groupBox.checked) api.model.selectedKeys.add(row.id);
        else api.model.selectedKeys.delete(row.id);
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
    ["", "Note", "Slug", "Folder", "Component"].forEach(text => headRow.createEl("th", { text }));

    const tbody = table.createEl("tbody");

    for (const row of groupRows) {
      const tr = tbody.createEl("tr");

      const selectCell = tr.createEl("td");
      const itemBox = selectCell.createEl("input", { type: "checkbox" });
      itemBox.checked = api.model.selectedKeys.has(row.id);
      itemBox.onchange = async () => {
        if (itemBox.checked) api.model.selectedKeys.add(row.id);
        else api.model.selectedKeys.delete(row.id);

        await api.saveCurrentState({ quiet: true, action: "selection" });
        api.render();
      };

      const noteCell = tr.createEl("td");
      api.createInternalLink(noteCell, row.path, row.name);

      tr.createEl("td", { text: row.slug });
      tr.createEl("td", { text: row.folder });
      tr.createEl("td", { text: row.component });
    }
  }
}

async function saveSelectionManifest(api) {
  const selectedRows = api.getSelectedRows();
  const items = selectedRows.map((row, index) => serializeTocRow(row, index));
  const extras = tocSavedSelectionExtras({ rows: items, tocPath: CONFIG.tocPath });

  const timestamp = new Date().toISOString();
  const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const manifestPath = getManifestPath(app, "content-index");
  const manifest = {
    type: "operation_manifest",
    recordType: "operation_manifest",
    timestamp,
    savedAt: timestamp,
    saved_at: timestamp,
    operation: "content-index",
    queryName: "Content Index",
    namespace: "content-index",
    vaultName,
    vault: vaultName,
    vaultRoot,
    queryPath,
    options: {
      selection_source: "content-index",
      selection_kind: "toc-entry",
      selection_key: "id",
      contents_prefix: CONFIG.contentsPrefix,
      toc_path: CONFIG.tocPath,
      default_component: CONFIG.defaultComponent,
      ...extras
    },
    count: items.length,
    items
  };
  writeJsonFile(manifestPath, manifest);


  await api.saveCurrentState({ quiet: true, action: "manifest" });
  api.notify(`Saved ${items.length} selected item(s) to ${manifestPath}`);

}


const {
  tocFile,
  groups,
  linkedContentPaths,
  badTocLinks
} = await buildTocGroups({
  app,
  tocPath: CONFIG.tocPath,
  contentsPrefix: CONFIG.contentsPrefix,
  defaultComponent: CONFIG.defaultComponent,
  ungroupedHeading: CONFIG.ungroupedHeading
});

if (!tocFile) {
  renderMissingToc(dv.container, { tocPath: CONFIG.tocPath });
  return;
}

const unlinkedContentFiles = findUnlinkedContentFiles({
  app,
  linkedContentPaths,
  contentsPrefix: CONFIG.contentsPrefix
});

const rows = groups.flatMap(group => group.items);

if (rows.length === 0) {
  renderEmptyWithAudit({ tocFile, badTocLinks, unlinkedContentFiles });
  return;
}

await renderSelectionQuery({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,

  title: "Content Index",
  namespace: "content-index",
  bridgeName: "__contentIndexSelection",

  vaultName,
  queryPath,
  stateVersion: 3,
  tempRoot: CONFIG.tempRoot,

  rows,
  columns: [],
  filterFields: [
    { key: "folder", title: "Folder" },
    { key: "component", title: "Component" }
  ],
  sortModes: [],
  defaultSortMode: "toc",

  selectionKind: "toc-entry",
  selectionKey: "id",
  serializeRow: serializeTocRow,
  savedSelectionExtras({ rows }) {
    return tocSavedSelectionExtras({ rows, tocPath: CONFIG.tocPath });
  },

  emptyMessage: "No public slugged TOC entries found.",
  noMatchesMessage: "No matching TOC entries.",

  summaryText({ displayedRows, selectedRows }) {
    const visibleHeadingCount = new Set(displayedRows.map(row => row.heading)).size;
    return `${visibleHeadingCount} heading group(s) · ${displayedRows.length} public slugged TOC file(s) displayed · ${selectedRows.length} checked · ${badTocLinks.length} TOC link issue(s) · ${unlinkedContentFiles.length} unlinked public slugged content file(s)`;
  },

  renderSummaryExtras(parent, { api }) {
    renderTocAuditSections(parent, {
      tocFile,
      badTocLinks,
      unlinkedContentFiles
    }, api.createInternalLink);
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
