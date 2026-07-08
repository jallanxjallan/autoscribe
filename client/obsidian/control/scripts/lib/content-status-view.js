function makeContentStatusView({
  app,
  dv,
  nodeRequire,
  queryPath,
  vaultName,
  config,
  renderSelectionQuery,
}) {
  const CONFIG = {
    tempRoot: "",
    debug: false,

    defaultStatus: "—",
    defaultStage: "—",
    defaultOrigin: "—",
    defaultSlugPrefix: "—",

    slugPrefixes: ["cnt", "img"],

    excludePaths: [
      ".obsidian",
      ".trash",
      ".autoscribe",
    ],

    ...(config || {}),
  };

  function asText(value, fallback = "") {
    if (value == null) return fallback;
    if (Array.isArray(value)) return value.map(v => String(v)).join(", ");
    const text = String(value).trim();
    return text || fallback;
  }

  function normalizePath(path) {
    return String(path || "")
      .replace(/\\/g, "/")
      .replace(/^\/+/, "");
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

  function normalizeSlug(slug) {
    return asText(slug).toLowerCase().trim();
  }

  function configuredSlugPrefixes() {
    return CONFIG.slugPrefixes
      .map(prefix => String(prefix || "").toLowerCase().trim().replace(/[.\-_/|:]+$/, ""))
      .filter(Boolean);
  }

  function slugHead(slug) {
    const clean = normalizeSlug(slug);
    return clean.split(/[.\-_/|:]/)[0] || "";
  }

  function slugPrefix(slug) {
    const head = slugHead(slug);
    if (!head) return CONFIG.defaultSlugPrefix;
    return configuredSlugPrefixes().includes(head) ? head : CONFIG.defaultSlugPrefix;
  }

  function slugMatchesCriteria(slug) {
    const head = slugHead(slug);
    if (!head) return false;
    return configuredSlugPrefixes().includes(head);
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
    if (!slugMatchesCriteria(slug)) return null;

    return page;
  }

  function allSluggedPages() {
    return app.vault.getMarkdownFiles()
      .map(file => sluggedPageForPath(file.path))
      .filter(Boolean);
  }

  function statusRowFromPage(page) {
    const path = normalizePath(page.file.path);
    const slug = asText(page.slug);
    const title = titleForPage(page);

    return {
      id: slug,
      selection_key: slug,

      path,
      name: title,
      title,
      slug,

      slug_prefix: slugPrefix(slug),

      status: asText(page.status, CONFIG.defaultStatus),
      stage: asText(page.stage, CONFIG.defaultStage),
      origin: asText(page.origin, CONFIG.defaultOrigin),
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
      status: row.status,
      stage: row.stage,
      origin: row.origin,
    };
  }

  function savedSelectionExtras({ rows }) {
    return {
      ordering: "content-status",
      displayed_count: rows.length,
      filters: ["status", "stage", "origin"],
      sort_modes: ["title"],
      slug_prefixes: CONFIG.slugPrefixes,
    };
  }

  function sortRows(rows, mode) {
    const copy = [...rows];

    if (mode === "title-desc") {
      return copy.sort((a, b) => alphaCompare(b, a));
    }

    return copy.sort(alphaCompare);
  }

  function setTriState(box, checkedCount, totalCount) {
    box.checked = totalCount > 0 && checkedCount === totalCount;
    box.indeterminate = checkedCount > 0 && checkedCount < totalCount;
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
      "Status",
      "Stage",
      "Origin",
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

      tr.createEl("td", { text: row.status });
      tr.createEl("td", { text: row.stage });
      tr.createEl("td", { text: row.origin });
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
        filters: ["status", "stage", "origin"],
        sort_modes: ["title"],
        slug_prefixes: CONFIG.slugPrefixes,
      },
      savedSelectionExtras({ rows }) {
        return savedSelectionExtras({ rows });
      }
    });
  }

  async function render() {
    const rows = buildRows();

    if (!rows.length) {
      dv.container.innerHTML = "";
      dv.paragraph(`No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`);
      return;
    }

    await renderSelectionQuery({
      app,
      dv,
      nodeRequire,

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
        { key: "status", title: "Status" },
        { key: "stage", title: "Stage" },
        { key: "origin", title: "Origin" },
      ],

      sortModes: [
        ["title-asc", "Title A–Z"],
        ["title-desc", "Title Z–A"],
      ],

      defaultSortMode: "title-asc",

      selectionKind: "slug",
      selectionKey: "slug",
      serializeRow: serializeStatusRow,
      savedSelectionExtras({ rows }) {
        return savedSelectionExtras({ rows });
      },

      emptyMessage: `No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`,
      noMatchesMessage: "No matching content-status rows.",

      summaryText({ displayedRows, selectedRows }) {
        return `${displayedRows.length} content file(s) displayed · ${selectedRows.length} checked`;
      },

      renderActions(parent, api) {
        const saveButton = parent.createEl("button", { text: "Save selection manifest" });
        saveButton.onclick = async () => {
          await saveSelectionManifest(api);
        };
      },

      renderResults: renderGroupedResults,

      debug: CONFIG.debug,
    });
  }

  return { render };
}

module.exports = {
  makeContentStatusView,
};
