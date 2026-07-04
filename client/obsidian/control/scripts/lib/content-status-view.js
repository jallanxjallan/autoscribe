"use strict";

const { makeContentStatusModel } = require("./content-status-model.js");
const { setTriState } = require("./dom.js");

function makeContentStatusView({ app, dv, nodeRequire, queryPath, vaultName, config, renderSelectionQuery }) {
  const modelBuilder = makeContentStatusModel({ app, dv, config });

  function renderGroupedResults(parent, displayedRows, api) {
    const sortedRows = modelBuilder.build().sortRows(displayedRows, api.model.sortMode || "title-asc");
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
    ["", "Title", "Status", "Stage", "Process", "Modified"].forEach(text => headRow.createEl("th", { text }));

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
      tr.createEl("td", { text: row.process });
      tr.createEl("td", { text: row.modified_display });
    }
  }

  async function saveSelectionManifest(api, state) {
    await api.saveDataviewSelection({
      operation: "content-status",
      queryName: "Content Status",
      namespace: "content-status",
      selectionSource: "content-status",
      selectionKind: "slug",
      selectionKey: "slug",
      serializeRow: state.serializeRow,
      options: {
        filters: ["status", "stage", "process"],
        sort_modes: ["title", "modified"],
      },
      savedSelectionExtras: state.savedSelectionExtras,
    });
  }

  async function render() {
    const state = modelBuilder.build();

    if (!state.rows.length) {
      dv.container.innerHTML = "";
      dv.paragraph("No Markdown files with frontmatter `slug` were found.");
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
      stateVersion: 2,
      tempRoot: config.tempRoot,
      rows: state.rows,
      columns: [],
      filterFields: [
        { key: "status", title: "Status" },
        { key: "stage", title: "Stage" },
        { key: "process", title: "Process" },
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
      serializeRow: state.serializeRow,
      savedSelectionExtras: state.savedSelectionExtras,
      emptyMessage: "No Markdown files with frontmatter `slug` were found.",
      noMatchesMessage: "No matching slugged files.",
      summaryText({ displayedRows, selectedRows }) {
        return `${displayedRows.length} slugged file(s) displayed · ${selectedRows.length} checked`;
      },
      renderActions(parent, api) {
        const saveButton = parent.createEl("button", { text: "Save selection manifest" });
        saveButton.onclick = async () => saveSelectionManifest(api, state);
      },
      renderResults: renderGroupedResults,
      sortRows: state.sortRows,
      debug: config.debug,
    });
  }

  return { render };
}

module.exports = { makeContentStatusView };
