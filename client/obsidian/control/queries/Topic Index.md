```dataviewjs
const CONFIG = {
  tempRoot: "",
  debug: false,

  // Topic Index includes only files with one of these slug prefixes.
  slugPrefixes: ["tpc", "fnd"],

  defaultStatus: "—",
  defaultTopic: "—",
  defaultTag: "—",

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
const runtime = createQueryRuntime({ app, queryTitle: "Topic Index query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { setTriState } = loader.requireControl("scripts/lib/dom.js");

function asList(value) {
  if (value == null) return [];

  if (Array.isArray(value)) {
    return value.flatMap(asList);
  }

  if (
    typeof value === "object" &&
    typeof value[Symbol.iterator] === "function"
  ) {
    return Array.from(value).flatMap(asList);
  }

  const text = String(value).trim();
  return text ? [text] : [];
}

function uniqueSorted(values) {
  return [...new Set(
    values
      .map(value => String(value || "").trim())
      .filter(Boolean)
  )].sort((a, b) => a.localeCompare(b));
}

function asText(value, fallback = "") {
  const values = asList(value);
  return values.length ? values.join(", ") : fallback;
}

function normalizePath(path) {
  return String(path || "").replace(/^\/+/, "");
}

function normalizeSlug(value) {
  return asText(value).toLowerCase().trim();
}

function normalizeTag(value) {
  return String(value || "")
    .trim()
    .replace(/^#/, "");
}

function isUnderscoreFolder(path) {
  return normalizePath(path)
    .split("/")
    .slice(0, -1)
    .some(part => part.startsWith("_"));
}

function isExcludedPath(path) {
  const clean = normalizePath(path);

  if (isUnderscoreFolder(clean)) return true;

  return CONFIG.excludePaths.some(prefix => {
    const cleanPrefix = normalizePath(prefix).replace(/\/+$/, "");
    return clean === cleanPrefix || clean.startsWith(`${cleanPrefix}/`);
  });
}

function slugPrefixForSlug(slug) {
  const cleanSlug = normalizeSlug(slug);
  if (!cleanSlug) return "—";

  const explicitPrefix = CONFIG.slugPrefixes.find(prefix => {
    const cleanPrefix = String(prefix || "").toLowerCase().trim();
    return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
  });

  if (explicitPrefix) return String(explicitPrefix).toLowerCase().trim();

  return cleanSlug.split(/[.\-_/]/)[0] || "—";
}

function slugMatchesCriteria(slug) {
  const cleanSlug = normalizeSlug(slug);
  if (!cleanSlug) return false;

  return CONFIG.slugPrefixes.some(prefix => {
    const cleanPrefix = String(prefix || "").toLowerCase().trim();
    return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
  });
}

function filenameStemForFile(file, fallback = "") {
  return (
    asText(file?.basename) ||
    asText(String(file?.name || "").replace(/\.[^.]+$/, "")) ||
    asText(fallback) ||
    asText(file?.path)
  );
}

function candidateMarkdownFiles() {
  return app.vault.getMarkdownFiles()
    .filter(file => !isExcludedPath(file.path))
    .filter(file => normalizePath(file.path) !== normalizePath(queryPath))
    .sort((a, b) => String(a.path).localeCompare(String(b.path)));
}

function pageForFile(file) {
  if (!file || isExcludedPath(file.path)) return null;
  return dv.page(file.path) || null;
}

function statusesForPage(page) {
  const statuses = uniqueSorted(asList(page?.status));
  return statuses.length ? statuses : [CONFIG.defaultStatus];
}

function tagsForPage(page) {
  const explicitTags = asList(page?.tags).map(normalizeTag).filter(Boolean);
  const fileTags = asList(page?.file?.tags).map(normalizeTag).filter(Boolean);
  const tags = uniqueSorted([...explicitTags, ...fileTags]);

  return tags.length ? tags : [CONFIG.defaultTag];
}

function topicsForPage(page) {
  const topics = uniqueSorted(asList(page?.topic));
  return topics.length ? topics : [CONFIG.defaultTopic];
}

function kindForPrefix(prefix) {
  if (prefix === "tpc") return "Topic";
  if (prefix === "fnd") return "Finding";
  return prefix || "—";
}

function entityRowFromPage(page, file) {
  const path = normalizePath(file.path);
  const slug = asText(page?.slug);
  const slugPrefix = slugPrefixForSlug(slug);
  const filename = filenameStemForFile(file);

  const statuses = statusesForPage(page);
  const tags = tagsForPage(page);
  const topics = topicsForPage(page);

  const modifiedMillis = page?.file?.mtime?.toMillis?.() ?? page?.file?.mtime ?? 0;

  return {
    id: slug,
    selection_key: slug,

    path,
    name: filename,
    title: filename,
    file_name: filename,
    slug,
    slug_prefix: slugPrefix,
    kind: kindForPrefix(slugPrefix),

    statuses,
    tags,
    topics,

    status_display: statuses.join(", "),
    tag_display: tags.join(", "),
    topic_display: topics.join(", "),

    modified: modifiedMillis,
    modified_display: modifiedMillis
      ? window.moment(modifiedMillis).format("YYYY-MM-DD HH:mm")
      : "",
  };
}

function buildEntityRows() {
  const rows = [];
  const seenSlugs = new Set();

  for (const file of candidateMarkdownFiles()) {
    const page = pageForFile(file);
    if (!page) continue;

    const slug = asText(page?.slug);
    if (!slugMatchesCriteria(slug)) continue;

    const cleanSlug = normalizeSlug(slug);
    if (seenSlugs.has(cleanSlug)) continue;
    seenSlugs.add(cleanSlug);

    rows.push(entityRowFromPage(page, file));
  }

  return rows.sort((a, b) => {
    const kindDiff = String(a.slug_prefix).localeCompare(String(b.slug_prefix));
    if (kindDiff !== 0) return kindDiff;

    return String(a.title || a.path).localeCompare(String(b.title || b.path));
  });
}

function buildFilterRows(entityRows) {
  const rows = [];

  for (const entity of entityRows) {
    for (const status of entity.statuses) {
      for (const tag of entity.tags) {
        for (const topic of entity.topics) {
          rows.push({
            ...entity,

            // Keep the real selection key stable. Multiple filter rows for the
            // same file all point back to the same selected file.
            selection_key: entity.selection_key,

            // Scalar fields for the shared selector.
            status,
            tag,
            topic,

            // Internal helper for rendering/deduping.
            entity,
            filter_key: `${entity.selection_key}::${status}::${tag}::${topic}`,
          });
        }
      }
    }
  }

  return rows;
}

function entityFromRow(row) {
  return row?.entity || row;
}

function uniqueEntityRows(rows) {
  const byKey = new Map();

  for (const row of rows) {
    const entity = entityFromRow(row);
    if (!entity?.selection_key) continue;
    if (!byKey.has(entity.selection_key)) byKey.set(entity.selection_key, entity);
  }

  return [...byKey.values()];
}

function uniqueSelectionKeys(rows) {
  return new Set(
    uniqueEntityRows(rows)
      .map(row => row.selection_key)
      .filter(Boolean)
  );
}

function serializeIndexRow(row) {
  const entity = entityFromRow(row);

  return {
    selection_key: entity.selection_key,
    slug: entity.slug,
    title: entity.title,
    path: entity.path,
    kind: entity.kind,
    slug_prefix: entity.slug_prefix,

    status: entity.statuses,
    status_display: entity.status_display,

    topic: entity.topics,
    topic_display: entity.topic_display,

    tag: entity.tags,
    tag_display: entity.tag_display,

    modified: entity.modified_display,
  };
}

function savedSelectionExtras({ rows }) {
  const entityRows = uniqueEntityRows(rows);

  return {
    ordering: "kind-title",
    slug_prefixes: CONFIG.slugPrefixes,
    displayed_count: entityRows.length,
    topic_count: entityRows.filter(row => row.slug_prefix === "tpc").length,
    finding_count: entityRows.filter(row => row.slug_prefix === "fnd").length,
  };
}

function groupRows(displayedRows) {
  const entityRows = uniqueEntityRows(displayedRows);

  const groups = [
    {
      key: "tpc",
      title: "Topics",
      rows: entityRows.filter(row => row.slug_prefix === "tpc"),
    },
    {
      key: "fnd",
      title: "Findings",
      rows: entityRows.filter(row => row.slug_prefix === "fnd"),
    },
  ];

  const known = new Set(groups.flatMap(group => group.rows.map(row => row.selection_key)));
  const otherRows = entityRows.filter(row => !known.has(row.selection_key));

  if (otherRows.length) {
    groups.push({ key: "other", title: "Other", rows: otherRows });
  }

  return groups.filter(group => group.rows.length);
}

function sortRows(rows) {
  return [...rows].sort((a, b) =>
    String(a.title || a.path).localeCompare(String(b.title || b.path))
  );
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
    "Status",
    "Topic",
    "Tags",
    "Modified",
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

    tr.createEl("td", { text: row.status_display });
    tr.createEl("td", { text: row.topic_display });
    tr.createEl("td", { text: row.tag_display });
    tr.createEl("td", { text: row.modified_display });
  }
}

function renderIndexResults(parent, displayedRows, api) {
  for (const group of groupRows(displayedRows)) {
    const section = parent.createDiv();
    renderGroupHeading(section, group, api);
    renderRowsTable(section, group.rows, api);
  }
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
      filters: ["status", "tag", "topic"],
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
    { key: "status", title: "Status" },
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

  emptyMessage: `No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`,
  noMatchesMessage: "No matching topic or finding files.",

  summaryText({ displayedRows, selectedRows }) {
    const displayedEntities = uniqueEntityRows(displayedRows);
    const displayedSelectedKeys = uniqueSelectionKeys(displayedRows);
    const selectedVisibleCount = [...displayedSelectedKeys]
      .filter(key => selectedRows.some(row => row.selection_key === key))
      .length;

    const topicCount = displayedEntities.filter(row => row.slug_prefix === "tpc").length;
    const findingCount = displayedEntities.filter(row => row.slug_prefix === "fnd").length;

    return `${topicCount} topic(s) · ${findingCount} finding(s) · ${selectedVisibleCount} checked`;
  },

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