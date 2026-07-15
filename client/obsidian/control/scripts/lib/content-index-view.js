"use strict";

const { makeContentIndexModel } = require("./content-index-model.js");
const { setTriState } = require("./dom.js");

function makeContentIndexView({ app, dv, nodeRequire, queryPath, vaultName, config, renderSelectionQuery }) {
  const modelBuilder = makeContentIndexModel({ app, dv, queryPath, config });

  function rowBelongsToHeading(row, heading) {
    const headingPath = heading.path || [];
    const rowPath = row.heading_path || [];
    if (headingPath.length > rowPath.length) return false;
    return headingPath.every((part, index) => rowPath[index] === part);
  }

  function rowsForHeading(displayedRows, heading) {
    return displayedRows.filter(row => rowBelongsToHeading(row, heading));
  }

  function renderHeadingBlock(parent, heading, headingRows, api) {
    if (!headingRows.length) return;

    const section = parent.createDiv();
    section.style.marginBottom = "1em";
    section.style.marginLeft = `${Math.max(0, heading.level - 1) * 1.25}em`;

    const headingRow = section.createDiv();
    headingRow.style.display = "flex";
    headingRow.style.alignItems = "center";
    headingRow.style.gap = "0.6em";
    headingRow.style.marginBottom = "0.4em";

    const checkedCount = headingRows.filter(row => api.model.selectedKeys.has(row.selection_key)).length;
    const groupBox = headingRow.createEl("input", { type: "checkbox" });
    setTriState(groupBox, checkedCount, headingRows.length);

    groupBox.onchange = async () => {
      for (const row of headingRows) {
        if (groupBox.checked) api.model.selectedKeys.add(row.selection_key);
        else api.model.selectedKeys.delete(row.selection_key);
      }
      await api.saveCurrentState({ quiet: true, action: "selection" });
      api.render();
    };

    const headingTag = heading.level === 1 ? "h2" : heading.level === 2 ? "h3" : "h4";
    const label = headingRow.createEl(headingTag, { text: heading.title });
    label.style.margin = "0";

    const countText = headingRow.createEl("span");
    countText.style.opacity = "0.75";
    countText.setText(`(${checkedCount}/${headingRows.length})`);
  }

  function renderRowsTable(parent, rows, api, sortRows) {
    const sortedRows = sortRows(rows);
    const tableWrap = parent.createDiv();
    tableWrap.style.overflowX = "auto";
    tableWrap.style.marginBottom = "1.2em";

    const table = tableWrap.createEl("table");
    table.classList.add("dataview", "table-view-table");
    table.style.width = "100%";

    const thead = table.createEl("thead");
    const headRow = thead.createEl("tr");
    ["", "Title", "Class", "Tags", "Layout component"].forEach(text => headRow.createEl("th", { text }));

    const tbody = table.createEl("tbody");
    for (const row of sortedRows) {
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
      tr.createEl("td", { text: row.class });
      tr.createEl("td", { text: row.tags_display });
      tr.createEl("td", { text: row.layout_component });
    }
  }

  function renderIndexResults(parent, displayedRows, api, state) {
    const tocRows = displayedRows.filter(row => row.placement !== "unplaced");
    const unplacedRows = displayedRows.filter(row => row.placement === "unplaced");
    const orderedHeadings = [...state.headings].sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
    const renderedRowKeys = new Set();

    for (const heading of orderedHeadings) {
      const directRows = state.sortRows(tocRows.filter(row => row.heading_key === heading.key));
      const subtreeRows = rowsForHeading(tocRows, heading);
      if (!directRows.length && !subtreeRows.length) continue;

      renderHeadingBlock(parent, heading, subtreeRows, api);

      if (directRows.length) {
        const section = parent.createDiv();
        section.style.marginLeft = `${Math.max(0, heading.level - 1) * 1.25}em`;
        renderRowsTable(section, directRows, api, state.sortRows);
        for (const row of directRows) renderedRowKeys.add(row.selection_key);
      }
    }

    const orphanRows = tocRows.filter(row => !renderedRowKeys.has(row.selection_key));
    if (orphanRows.length) {
      const heading = { key: "Contents", title: "Contents", level: 1, path: ["Contents"], order: 999999 };
      renderHeadingBlock(parent, heading, orphanRows, api);
      renderRowsTable(parent, orphanRows, api, state.sortRows);
    }

    if (unplacedRows.length) {
      const heading = { key: "Not in table of contents", title: "Not in table of contents", level: 1, path: ["Not in table of contents"], order: 1000000 };
      renderHeadingBlock(parent, heading, unplacedRows, api);
      renderRowsTable(parent, unplacedRows, api, state.sortRows);
    }
  }

  function renderLinkHealth(parent, linkHealth, api) {
    const missing = linkHealth?.missing || [];
    const duplicates = linkHealth?.duplicates || [];
    if (!missing.length && !duplicates.length) return;

    const section = parent.createDiv();
    section.style.marginTop = "1.6em";
    section.style.paddingTop = "0.8em";
    section.style.borderTop = "1px solid var(--background-modifier-border)";
    section.createEl("h3", { text: "Link health" });

    if (missing.length) {
      const missingBlock = section.createDiv();
      missingBlock.style.marginBottom = "1em";
      missingBlock.createEl("h4", { text: `Missing TOC links (${missing.length})` });
      const table = missingBlock.createEl("table");
      table.classList.add("dataview", "table-view-table");
      table.style.width = "100%";
      const thead = table.createEl("thead");
      const headRow = thead.createEl("tr");
      ["Target", "Heading", "Line", "TOC item"].forEach(text => headRow.createEl("th", { text }));
      const tbody = table.createEl("tbody");
      for (const item of missing) {
        const tr = tbody.createEl("tr");
        tr.createEl("td", { text: item.target });
        tr.createEl("td", { text: item.heading_key || "Contents" });
        tr.createEl("td", { text: String(item.lineNumber || "") });
        tr.createEl("td", { text: item.lineText || "" });
      }
    }

    if (duplicates.length) {
      const duplicateBlock = section.createDiv();
      duplicateBlock.createEl("h4", { text: `Duplicate TOC placements (${duplicates.length})` });
      const table = duplicateBlock.createEl("table");
      table.classList.add("dataview", "table-view-table");
      table.style.width = "100%";
      const thead = table.createEl("thead");
      const headRow = thead.createEl("tr");
      ["File", "Count", "Placements"].forEach(text => headRow.createEl("th", { text }));
      const tbody = table.createEl("tbody");
      for (const item of duplicates) {
        const tr = tbody.createEl("tr");
        const fileCell = tr.createEl("td");
        api.createInternalLink(fileCell, item.path, item.basename || item.path);
        tr.createEl("td", { text: String(item.placements.length) });
        const placementsCell = tr.createEl("td");
        const list = placementsCell.createEl("ul");
        list.style.margin = "0";
        list.style.paddingLeft = "1.2em";
        for (const placement of item.placements) {
          const li = list.createEl("li");
          li.setText(`line ${placement.lineNumber}: ${placement.heading_key || "Contents"}`);
        }
      }
    }
  }

  function renderSelectedTocLink(parent, api, selectedTocFile) {
    if (!selectedTocFile) {
      const sourceWrap = parent.createDiv();
      sourceWrap.style.marginBottom = "0.8em";
      sourceWrap.createEl("span", { text: "No table of contents found. Showing matching files alphabetically." });
      return;
    }

    const sourceWrap = parent.createDiv();
    sourceWrap.style.display = "flex";
    sourceWrap.style.alignItems = "center";
    sourceWrap.style.gap = "0.4em";
    sourceWrap.style.marginBottom = "0.8em";
    sourceWrap.createEl("span", { text: "Source:" });
    api.createInternalLink(sourceWrap, selectedTocFile.path, selectedTocFile.basename);
  }

  function copyToClipboard(text) {
    const value = String(text || "");
    if (navigator?.clipboard?.writeText) return navigator.clipboard.writeText(value);
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    return Promise.resolve();
  }

  function renderUnicodeReference(parent) {
    const details = parent.createEl("details");
    details.style.margin = "0.8em 0";
    details.createEl("summary", { text: "Unicode symbol reference" });
    const table = details.createEl("table");
    table.classList.add("dataview", "table-view-table");
    table.style.marginTop = "0.5em";
    const thead = table.createEl("thead");
    const headRow = thead.createEl("tr");
    ["Symbol", "Code", "Label", "Meaning", "Copy"].forEach(text => headRow.createEl("th", { text }));
    const tbody = table.createEl("tbody");
    for (const item of config.unicodeReference) {
      const tr = tbody.createEl("tr");
      tr.createEl("td", { text: item.symbol });
      tr.createEl("td", { text: item.code });
      tr.createEl("td", { text: item.label });
      tr.createEl("td", { text: item.meaning });
      const copyCell = tr.createEl("td");
      const copyButton = copyCell.createEl("button", { text: "Copy" });
      copyButton.onclick = async () => {
        await copyToClipboard(item.symbol);
        copyButton.setText("Copied");
        window.setTimeout(() => copyButton.setText("Copy"), 900);
      };
    }
  }

  async function saveSelectionManifest(api, state) {
    await api.saveDataviewSelection({
      operation: "content-index",
      queryName: "Content Index",
      namespace: "content-index",
      selectionSource: "content-index",
      selectionKind: "content-index",
      selectionKey: "selection_key",
      serializeRow: state.serializeRow,
      options: {
        toc_path: state.selectedTocFile?.path || "",
        ordering: state.selectedTocFile ? "table-of-contents" : "alphabetical",
        slug_prefixes: config.slugPrefixes,
        filters: ["slug_prefix", "class", "tag_values", "layout_component"],
      },
      savedSelectionExtras: state.savedSelectionExtras,
    });
  }

  async function render() {
    const state = await modelBuilder.build();
    if (!state.rows.length) {
      dv.container.innerHTML = "";
      dv.paragraph(`No Markdown files matched slug prefixes ${config.slugPrefixes.join(", ")}.`);
      return;
    }

    await renderSelectionQuery({
      app,
      dv,
      nodeRequire,
      title: "Content Index",
      namespace: "content-index",
      bridgeName: "__contentIndexSelection",
      vaultName,
      queryPath,
      stateVersion: 2,
      tempRoot: config.tempRoot,
      rows: state.rows,
      columns: [],
      filterFields: [
        { key: "slug_prefix", title: "Slug prefix" },
        { key: "class", title: "Class" },
        { key: "tag_values", title: "Tags" },
        { key: "layout_component", title: "Layout component" },
      ],
      sortModes: [["toc", "TOC order"]],
      defaultSortMode: "toc",
      selectionKind: "content-index",
      selectionKey: "selection_key",
      serializeRow: state.serializeRow,
      savedSelectionExtras: state.savedSelectionExtras,
      emptyMessage: state.selectedTocFile
        ? `No Markdown files linked from ${state.selectedTocFile.path} were found.`
        : "No matching Markdown files were found.",
      noMatchesMessage: "No matching files.",
      summaryText({ displayedRows, selectedRows }) {
        const tocCount = displayedRows.filter(row => row.placement === "toc").length;
        const alphaCount = displayedRows.filter(row => row.placement === "alphabetical").length;
        const unplacedCount = displayedRows.filter(row => row.placement === "unplaced").length;
        if (state.selectedTocFile) return `${tocCount} TOC file(s) · ${unplacedCount} not in TOC · ${selectedRows.length} checked`;
        return `${alphaCount} file(s) alphabetically · ${selectedRows.length} checked`;
      },
      renderActions(parent, api) {
        renderSelectedTocLink(parent, api, state.selectedTocFile);
        renderUnicodeReference(parent);
        const saveButton = parent.createEl("button", { text: "Save selection manifest" });
        saveButton.onclick = async () => saveSelectionManifest(api, state);
      },
      renderResults(parent, displayedRows, api) {
        renderIndexResults(parent, displayedRows, api, state);
        renderLinkHealth(parent, state.linkHealth, api);
      },
      sortRows: state.sortRows,
      debug: config.debug,
    });
  }

  return { render };
}

module.exports = { makeContentIndexView };
