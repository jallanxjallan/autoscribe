```dataviewjs
const CONFIG = {
  tempRoot: "",
  debug: false,

  // Topic Index displays only files with one of these slug prefixes.
  slugPrefixes: ["tpc", "fnd"],

  defaultTopic: "—",
  defaultTag: "—",

  excludePaths: [
    ".obsidian",
    ".trash",
    ".autoscribe",
  ],

  // Shared selector displays this many choices before showing a more... link.
  maxFilterChoices: 5,
};

const nodeRequire =
  typeof require === "function"
    ? require
    : window.require;

const pathMod = nodeRequire("path");
const { Modal } = nodeRequire("obsidian");
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
const runtime = createQueryRuntime({ app, queryTitle: "Topic Index query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { setTriState } = loader.requireControl("scripts/lib/dom.js");
const rg = loader.requireControl("scripts/lib/rg.js");
const { createTopicIndexLogic } = loader.requireControl("scripts/lib/topic-index.js");

const logic = createTopicIndexLogic({
  app,
  dv,
  pathMod,
  vaultBasePath,
  queryPath,
  config: CONFIG,
  rg,
});

const {
  clearElement,
  buildEntityRows,
  buildFilterRows,
  serializeIndexRow,
  savedSelectionExtras,
  groupRows,
  sortRows,
  findBookmarkMatches,
  summaryText,
} = logic;

function slugPrefix(value) {
  return String(value || "").split(/[._-]/, 1)[0].toLowerCase();
}

function isContentFile(file, frontmatter) {
  const slug = frontmatter?.slug || file.basename;
  return ["cnt", "img"].includes(slugPrefix(slug));
}

function collectFrontmatterLinktexts(value, output = new Set()) {
  if (value == null) return output;

  if (Array.isArray(value)) {
    for (const item of value) collectFrontmatterLinktexts(item, output);
    return output;
  }

  if (typeof value === "object") {
    for (const item of Object.values(value)) {
      collectFrontmatterLinktexts(item, output);
    }
    return output;
  }

  if (typeof value !== "string") return output;

  for (const match of value.matchAll(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g)) {
    const linktext = match[1].trim();
    if (linktext) output.add(linktext);
  }

  return output;
}

function buildContentReferenceIndex() {
  const references = new Map();

  for (const file of app.vault.getMarkdownFiles()) {
    const cache = app.metadataCache.getFileCache(file);
    const frontmatter = cache?.frontmatter;
    if (!frontmatter || !isContentFile(file, frontmatter)) continue;

    const targetPaths = new Set();

    for (const linktext of collectFrontmatterLinktexts(frontmatter)) {
      const target = app.metadataCache.getFirstLinkpathDest(linktext, file.path);
      if (target) targetPaths.add(target.path);
    }

    for (const targetPath of targetPaths) {
      if (!references.has(targetPath)) references.set(targetPath, []);
      references.get(targetPath).push({
        path: file.path,
        title: frontmatter.title || file.basename,
      });
    }
  }

  for (const files of references.values()) {
    files.sort((a, b) => a.title.localeCompare(b.title));
  }

  return references;
}

const contentReferencesByTarget = buildContentReferenceIndex();

function showContentLinksModal(row, links, api) {
  class ContentLinksModal extends Modal {
    onOpen() {
      const { contentEl } = this;
      contentEl.empty();
      contentEl.createEl("h2", { text: `Content linked to ${row.title}` });

      if (!links.length) {
        contentEl.createEl("p", {
          text: "No content files link to this note through frontmatter.",
        });
        return;
      }

      const list = contentEl.createEl("ul");
      for (const link of links) {
        const item = list.createEl("li");
        api.createInternalLink(item, link.path, link.title);
      }
    }

    onClose() {
      this.contentEl.empty();
    }
  }

  new ContentLinksModal(app).open();
}

function renderGroupHeading(parent, group, api) {
  const headingRow = parent.createDiv();
  headingRow.style.display = "flex";
  headingRow.style.alignItems = "center";
  headingRow.style.gap = "0.6em";
  headingRow.style.margin = "1em 0 0.4em";

  const checkedCount = group.rows.filter(row =>
    api.model.selectedKeys.has(row.selection_key)
  ).length;

  const groupBox = headingRow.createEl("input", { type: "checkbox" });
  setTriState(groupBox, checkedCount, group.rows.length);

  groupBox.onchange = async () => {
    for (const row of group.rows) {
      if (groupBox.checked) api.model.selectedKeys.add(row.selection_key);
      else api.model.selectedKeys.delete(row.selection_key);
    }

    await api.saveCurrentState({ quiet: true, action: "selection" });
    api.render();
  };

  const label = headingRow.createEl("h2", { text: group.title });
  label.style.margin = "0";

  const countText = headingRow.createEl("span");
  countText.style.opacity = "0.75";
  countText.setText(`(${checkedCount}/${group.rows.length})`);
}

function renderRowsTable(parent, rows, api) {
  const tableWrap = parent.createDiv();
  tableWrap.style.overflowX = "auto";
  tableWrap.style.marginBottom = "1.2em";

  const table = tableWrap.createEl("table");
  table.classList.add("dataview", "table-view-table");
  table.style.width = "100%";

  const thead = table.createEl("thead");
  const headRow = thead.createEl("tr");

  [
    "",
    "File",
    "Topic",
    "Tags",
    "Content",
  ].forEach(text => headRow.createEl("th", { text }));

  const tbody = table.createEl("tbody");

  for (const row of sortRows(rows)) {
    const tr = tbody.createEl("tr");

    const selectCell = tr.createEl("td");
    const itemBox = selectCell.createEl("input", { type: "checkbox" });
    itemBox.checked = api.model.selectedKeys.has(row.selection_key);

    itemBox.onchange = async () => {
      if (itemBox.checked) api.model.selectedKeys.add(row.selection_key);
      else api.model.selectedKeys.delete(row.selection_key);

      await api.saveCurrentState({ quiet: true, action: "selection" });
      api.render();
    };

    const noteCell = tr.createEl("td");
    api.createInternalLink(noteCell, row.path, row.title);

    tr.createEl("td", { text: row.topic_display });
    tr.createEl("td", { text: row.tag_display });

    const contentCell = tr.createEl("td");
    const contentLinks = contentReferencesByTarget.get(row.path) || [];

    if (!contentLinks.length) {
      contentCell.setText("0");
    } else {
      const countLink = contentCell.createEl("a", {
        text: String(contentLinks.length),
        href: "#",
      });
      countLink.title = "Show linked content files";
      countLink.onclick = event => {
        event.preventDefault();
        showContentLinksModal(row, contentLinks, api);
      };
    }
  }
}

function renderIndexResults(parent, displayedRows, api) {
  for (const group of groupRows(displayedRows)) {
    const section = parent.createDiv();
    renderGroupHeading(section, group, api);
    renderRowsTable(section, group.rows, api);
  }
}

const bookmarkLookupState = { text: "" };

function renderBookmarkLookup(parent, { api }) {
  const wrap = parent.createDiv();
  wrap.style.marginTop = "0.75em";
  wrap.style.paddingTop = "0.75em";
  wrap.style.borderTop = "1px solid var(--background-modifier-border)";

  const label = wrap.createEl("label");
  label.style.display = "block";
  label.style.fontWeight = "600";
  label.style.marginBottom = "0.35em";
  label.setText("Bookmark search");

  const searchRow = wrap.createDiv();
  searchRow.style.display = "flex";
  searchRow.style.flexWrap = "wrap";
  searchRow.style.alignItems = "center";
  searchRow.style.gap = "0.5em";

  const input = searchRow.createEl("input", {
    type: "search",
    placeholder: "Paste a Google Docs bookmark URL or id.something",
    value: bookmarkLookupState.text,
  });
  input.style.flex = "1 1 28em";
  input.style.minWidth = "20em";
  input.style.boxSizing = "border-box";

  const searchButton = searchRow.createEl("button", { text: "Find bookmark" });

  const result = wrap.createDiv();
  result.style.marginTop = "0.45em";
  result.style.opacity = "0.75";
  result.setText("Paste a bookmark URL to find the matching Markdown note.");

  const runSearch = () => {
    bookmarkLookupState.text = input.value;
    clearElement(result);

    if (!input.value.trim()) {
      result.style.opacity = "0.75";
      result.setText("Paste a bookmark URL to find the matching Markdown note.");
      return;
    }

    searchButton.disabled = true;
    searchButton.setText("Searching...");
    result.style.opacity = "0.75";
    result.setText("Searching Markdown files with rg...");

    let bookmarkId = "";
    let matches = [];

    try {
      const found = findBookmarkMatches(input.value, entityRows);
      bookmarkId = found.bookmarkId;
      matches = found.matches;
    } catch (error) {
      console.error(error);
      clearElement(result);
      searchButton.disabled = false;
      searchButton.setText("Find bookmark");
      result.style.opacity = "0.75";
      result.setText(`Bookmark search failed: ${error.message || error}`);
      return;
    }

    clearElement(result);
    searchButton.disabled = false;
    searchButton.setText("Find bookmark");

    if (!bookmarkId) {
      result.style.opacity = "0.75";
      result.setText("No Google bookmark id found in that text.");
      return;
    }

    if (!matches.length) {
      result.style.opacity = "0.75";
      result.setText(`No Markdown file contains ${bookmarkId}.`);
      return;
    }

    result.style.opacity = "1";
    result.createEl("span", { text: `${bookmarkId} → ` });

    matches.forEach((match, index) => {
      if (index > 0) result.createEl("span", { text: ", " });

      api.createInternalLink(
        result,
        match.path,
        match.kind && match.kind !== "Unindexed"
          ? match.title || match.path
          : `${match.title || match.path} [unindexed]`
      );
    });
  };

  searchButton.onclick = runSearch;

  input.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });
}

async function saveSelectionManifest(api) {
  await api.saveDataviewSelection({
    operation: "topic-index",
    queryName: "Topic Index",
    namespace: "topic-index",
    selectionSource: "topic-index",
    selectionKind: "topic-index",
    selectionKey: "selection_key",
    serializeRow: serializeIndexRow,
    options: {
      ordering: "kind-title",
      slug_prefixes: CONFIG.slugPrefixes,
      filters: ["tag", "topic"],
      note: "Filter rows are scalar-expanded for selector behavior; rendered rows are deduped by selection_key.",
    },
    savedSelectionExtras({ rows }) {
      return savedSelectionExtras({ rows });
    }
  });
}

const entityRows = buildEntityRows();
const rows = buildFilterRows(entityRows);

if (!entityRows.length) {
  dv.container.innerHTML = "";
  dv.paragraph(`No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`);
  return;
}

await renderSelectionQuery({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,

  title: "Topic Index",
  namespace: "topic-index",
  bridgeName: "__topicIndexSelection",

  vaultName,
  queryPath,
  stateVersion: 2,
  tempRoot: CONFIG.tempRoot,

  rows,
  columns: [],

  filterFields: [
    { key: "tag", title: "Tag" },
    { key: "topic", title: "Topic" },
  ],

  sortModes: [
    ["kind-title", "Kind / title"],
  ],

  defaultSortMode: "kind-title",

  selectionKind: "topic-index",
  selectionKey: "selection_key",
  serializeRow: serializeIndexRow,
  savedSelectionExtras({ rows }) {
    return savedSelectionExtras({ rows });
  },

  maxFilterChoices: CONFIG.maxFilterChoices,

  emptyMessage: `No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`,
  noMatchesMessage: "No matching topic or finding files.",

  renderSummaryExtras(parent, context) {
    renderBookmarkLookup(parent, context);
  },

  summaryText,

  renderActions(parent, api) {
    const saveButton = parent.createEl("button", { text: "Save selection manifest" });
    saveButton.onclick = async () => {
      await saveSelectionManifest(api);
    };
  },

  renderResults: renderIndexResults,

  debug: CONFIG.debug
});
```
