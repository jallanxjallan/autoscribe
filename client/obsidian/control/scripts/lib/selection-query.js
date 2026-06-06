const { notify } = require("./notify");
const { setTriState } = require("./dom");
const { createInternalLink } = require("./internal-link");
const { forceCurrentLeafPresentation } = require("./workspace");
const { createSelectionModel } = require("./selection-model");
const { createStateStore } = require("../selections/selection-state");

function defaultSerializeRow(row, index) {
  return {
    order: index + 1,
    ...row
  };
}

function stateMatchesEnvelope(state, options) {
  return !!(
    state &&
    typeof state === "object" &&
    state.version === options.stateVersion &&
    state.namespace === options.namespace &&
    state.vault === options.vaultName &&
    state.queryPath === options.queryPath
  );
}

function buildSavedSelectionRecord({
  options,
  model,
  stateStore,
  action,
  timestamp
}) {
  const serializeRow = options.serializeRow ?? defaultSerializeRow;
  const rows = model.getSelectedRows().map((row, index) => serializeRow(row, index));
  const selectedValues = rows.map(row => row[options.selectionKey]);
  const selectedPaths = rows
    .map(row => row.path)
    .filter(path => typeof path === "string" && path.length > 0);

  const record = {
    type: "saved_selection",
    recordType: "saved_selection",
    timestamp,
    savedAt: timestamp,
    saved_at: timestamp,
    action,

    namespace: options.namespace,
    vaultName: options.vaultName,
    vault: options.vaultName,
    queryPath: options.queryPath,
    stateVersion: options.stateVersion,

    sessionToken: stateStore.sessionToken,
    stateFile: stateStore.stateFile,
    tempRoot: stateStore.tempRoot,
    fallbackStorageKey: stateStore.fallbackStorageKey,

    selectionKind: options.selectionKind,
    selectionKey: options.selectionKey,
    count: rows.length,

    selectedValues,
    values: selectedValues,
    selectedPaths,
    paths: selectedPaths,
    rows
  };

  if (options.selectionKey === "slug") {
    record.selectedSlugs = selectedValues;
    record.slugs = selectedValues;
  }

  if (typeof options.savedSelectionExtras === "function") {
    Object.assign(record, options.savedSelectionExtras({
      rows,
      action,
      timestamp,
      model,
      options
    }));
  }

  return record;
}

async function renderSelectionQuery(rawOptions) {
  const options = {
    stateVersion: 2,
    selectionKind: "slug",
    selectionKey: "slug",
    filterFields: [],
    sortModes: [],
    defaultSortMode: "slug",
    tempRoot: "",
    bridgeName: null,
    emptyMessage: "No rows found.",
    noMatchesMessage: "No matching rows.",
    summaryText: null,
    renderSummaryExtras: null,
    renderActions: null,
    renderResults: null,
    savedSelectionExtras: null,
    sortRows: null,
    serializeRow: defaultSerializeRow,
    debug: false,
    ...rawOptions
  };

  const {
    app,
    dv,
    nodeRequire,
    rows,
    columns
  } = options;

  if (!app) throw new Error("renderSelectionQuery requires app.");
  if (!dv) throw new Error("renderSelectionQuery requires dv.");
  if (!Array.isArray(rows)) throw new Error("renderSelectionQuery requires rows.");
  if (!Array.isArray(columns)) throw new Error("renderSelectionQuery requires columns.");

  await forceCurrentLeafPresentation(app);

  if (rows.length === 0) {
    dv.paragraph(options.emptyMessage);
    return null;
  }

  const model = createSelectionModel({
    rows,
    filterFields: options.filterFields,
    sortModes: options.sortModes,
    defaultSortMode: options.defaultSortMode,
    selectionKey: options.selectionKey,
    sortRows: options.sortRows
  });

  const stateStore = createStateStore({
    namespace: options.namespace,
    vaultName: options.vaultName,
    queryPath: options.queryPath,
    nodeRequire,
    notify,
    tempRoot: options.tempRoot
  });

  function debugLog(...args) {
    if (!options.debug) return;
    console.log(`[${options.namespace}]`, ...args);
  }

  function getApi() {
    return {
      app,
      dv,
      options,
      model,
      stateStore,
      rows,
      selectedKeys: model.selectedKeys,
      getSelectedRows: model.getSelectedRows,
      getDisplayedRows: model.getDisplayedRows,
      getSortMode: model.getSortMode,
      saveCurrentState,
      reloadSavedState,
      clearSavedState,
      render,
      notify,
      createInternalLink(parent, path, text) {
        createInternalLink(parent, app, path, text, async () => {
          await saveCurrentState({ quiet: true });
        });
      }
    };
  }

  function publishSelectionBridge(action = "selection", timestamp = new Date().toISOString()) {
    if (!options.bridgeName || typeof window === "undefined") return;

    const savedSelection = buildSavedSelectionRecord({
      options,
      model,
      stateStore,
      action,
      timestamp
    });

    window[options.bridgeName] = {
      ...savedSelection,
      saved_selection: savedSelection,
      updatedAt: timestamp
    };
  }

  function snapshotCurrentState(action = "selection") {
    const timestamp = new Date().toISOString();
    const filters = {};

    for (const group of model.filterGroups) {
      filters[group.key] = [...group.selected];
    }

    const savedSelection = buildSavedSelectionRecord({
      options,
      model,
      stateStore,
      action,
      timestamp
    });

    const state = {
      version: options.stateVersion,
      type: "saved_selection",
      recordType: "saved_selection",

      namespace: options.namespace,
      vault: options.vaultName,
      vaultName: options.vaultName,
      queryPath: options.queryPath,

      timestamp,
      savedAt: timestamp,
      saved_at: timestamp,
      saved_selection: savedSelection,

      sortMode: model.getSortMode(),
      filters,

      selectionKind: options.selectionKind,
      selectionKey: options.selectionKey,
      count: savedSelection.count,
      selectedValues: [...model.selectedKeys],
      selectedRows: savedSelection.rows,
      selectedPaths: savedSelection.paths
    };

    if (options.selectionKey === "slug") {
      state.selectedSlugs = [...model.selectedKeys];
    }

    return state;
  }

  function applySavedState(state) {
    if (!stateMatchesEnvelope(state, options)) return false;

    const validSortModes = model.getValidSortModes();
    if (validSortModes.has(state.sortMode)) {
      model.setSortMode(state.sortMode);
    }

    if (state.filters && typeof state.filters === "object") {
      for (const group of model.filterGroups) {
        const savedValues = state.filters[group.key];
        if (!Array.isArray(savedValues)) continue;

        const allowed = new Set(group.values);
        group.selected.clear();

        for (const value of savedValues) {
          if (allowed.has(value)) group.selected.add(value);
        }
      }
    }

    model.selectedKeys.clear();

    const savedKeys =
      Array.isArray(state.selectedValues)
        ? state.selectedValues
        : Array.isArray(state.selectedSlugs)
          ? state.selectedSlugs
          : [];

    const validKeys = model.getValidSelectionKeys();
    for (const value of savedKeys) {
      if (validKeys.has(value)) model.selectedKeys.add(value);
    }

    publishSelectionBridge(
      "restore",
      state.timestamp ?? state.savedAt ?? state.saved_at ?? new Date().toISOString()
    );

    return true;
  }

  async function saveCurrentState({ quiet = false, action = "selection" } = {}) {
    try {
      const state = snapshotCurrentState(action);
      await stateStore.write(state);
      publishSelectionBridge(action, state.timestamp);

      if (!quiet) notify(`${options.title ?? options.namespace} state saved.`);
      return true;
    } catch (error) {
      console.error(error);
      if (!quiet) notify(`Could not save ${options.title ?? options.namespace} state.`);
      return false;
    }
  }

  async function reloadSavedState({ quiet = false } = {}) {
    const state = await stateStore.read();

    if (!state) {
      if (!quiet) notify(`No saved ${options.title ?? options.namespace} state found.`);
      return false;
    }

    const loaded = applySavedState(state);

    if (!loaded) {
      if (!quiet) notify(`Saved ${options.title ?? options.namespace} state did not match this query.`);
      return false;
    }

    if (!quiet) notify(`${options.title ?? options.namespace} state reloaded.`);
    render();
    return true;
  }

  async function clearSavedState() {
    try {
      await stateStore.remove();
      model.reset();
      notify(`${options.title ?? options.namespace} state cleared.`);
      render();
    } catch (error) {
      console.error(error);
      notify(`Could not clear ${options.title ?? options.namespace} state.`);
    }
  }

  function installStateReloadHooks() {
    if (typeof window === "undefined") return;

    const safeVault = options.vaultName.replace(/[^a-z0-9._-]+/gi, "-");
    const safeQuery = options.queryPath.replace(/[^a-z0-9._-]+/gi, "-");
    const hookKey = `__selection_query_${options.namespace}_${safeVault}_${safeQuery}_${stateStore.sessionToken}`;

    try {
      const old = window[hookKey];

      if (old?.leafRef && typeof app.workspace.offref === "function") {
        app.workspace.offref(old.leafRef);
      }

      if (old?.focusHandler) {
        window.removeEventListener("focus", old.focusHandler);
      }
    } catch (_) {}

    const reloadIfActive = async () => {
      const active = app.workspace.getActiveFile();
      if (active?.path !== options.queryPath) return;
      await reloadSavedState({ quiet: true });
    };

    let leafRef = null;

    try {
      leafRef = app.workspace.on("active-leaf-change", reloadIfActive);
    } catch (_) {}

    try {
      window.addEventListener("focus", reloadIfActive);
    } catch (_) {}

    window[hookKey] = { leafRef, focusHandler: reloadIfActive };
  }

  function renderTopBlock(parent, selectedRows, displayedRows, selectedDisplayedCount) {
    const block = parent.createDiv();
    block.style.marginBottom = "1em";
    block.style.padding = "0.75em";
    block.style.border = "1px solid var(--background-modifier-border)";
    block.style.borderRadius = "8px";
    block.style.background = "var(--background-secondary)";

    const summary = block.createDiv();
    summary.style.marginBottom = "0.75em";

    if (typeof options.summaryText === "function") {
      summary.setText(options.summaryText({
        rows,
        selectedRows,
        displayedRows,
        selectedDisplayedCount
      }));
    } else {
      summary.setText(
        `${rows.length} rows indexed · ${displayedRows.length} displayed · ${selectedRows.length} checked`
      );
    }

    const api = getApi();

    if (typeof options.renderSummaryExtras === "function") {
      options.renderSummaryExtras(block, {
        rows,
        selectedRows,
        displayedRows,
        selectedDisplayedCount,
        api
      });
    }

    const buttonRow = block.createDiv();
    buttonRow.style.display = "flex";
    buttonRow.style.flexWrap = "wrap";
    buttonRow.style.alignItems = "center";
    buttonRow.style.gap = "0.5em";

    const reloadButton = buttonRow.createEl("button", { text: "Reload state" });
    reloadButton.onclick = async () => {
      await reloadSavedState();
    };

    const clearStateButton = buttonRow.createEl("button", { text: "Clear state" });
    clearStateButton.onclick = async () => {
      await clearSavedState();
    };

    const clearCheckedButton = buttonRow.createEl("button", { text: "Clear checked items" });
    clearCheckedButton.onclick = async () => {
      model.selectedKeys.clear();
      await saveCurrentState({ quiet: true, action: "clear" });
      render();
    };

    const displayedControls = block.createDiv();
    displayedControls.style.display = "flex";
    displayedControls.style.flexWrap = "wrap";
    displayedControls.style.alignItems = "center";
    displayedControls.style.gap = "1em";
    displayedControls.style.marginTop = "0.75em";

    const selectDisplayedLabel = displayedControls.createEl("label");
    selectDisplayedLabel.style.display = "flex";
    selectDisplayedLabel.style.alignItems = "center";
    selectDisplayedLabel.style.gap = "0.5em";

    const selectDisplayedBox = selectDisplayedLabel.createEl("input", { type: "checkbox" });
    setTriState(selectDisplayedBox, selectedDisplayedCount, displayedRows.length);

    selectDisplayedBox.onchange = async () => {
      for (const row of displayedRows) {
        const key = model.getRowKey(row);

        if (selectDisplayedBox.checked) model.selectedKeys.add(key);
        else model.selectedKeys.delete(key);
      }

      await saveCurrentState({ quiet: true, action: "selection" });
      render();
    };

    selectDisplayedLabel.appendText("Select all displayed items");

    if (options.sortModes.length > 0) {
      const sortWrap = displayedControls.createDiv();
      const sortLabel = sortWrap.createEl("label");
      sortLabel.style.display = "flex";
      sortLabel.style.alignItems = "center";
      sortLabel.style.gap = "0.5em";
      sortLabel.appendText("Sort by");

      const sortSelect = sortLabel.createEl("select");

      for (const [value, label] of options.sortModes) {
        const option = sortSelect.createEl("option", { text: label, value });
        option.selected = value === model.getSortMode();
      }

      sortSelect.onchange = async () => {
        model.setSortMode(sortSelect.value);
        await saveCurrentState({ quiet: true, action: "sort" });
        render();
      };
    }

    if (typeof options.renderActions === "function") {
      const actionBlock = block.createDiv();
      actionBlock.style.marginTop = "0.75em";
      options.renderActions(actionBlock, api);
    }

    const stateInfo = block.createDiv();
    stateInfo.style.marginTop = "0.75em";
    stateInfo.style.opacity = "0.75";
    stateInfo.setText(
      stateStore.stateFile
        ? `saved_selection state: ${stateStore.stateFile}`
        : "saved_selection state uses browser fallback storage."
    );

    const timestampInfo = block.createDiv();
    timestampInfo.style.marginTop = "0.35em";
    timestampInfo.style.opacity = "0.65";
    timestampInfo.setText("Saved record type: saved_selection; timestamp field: timestamp");
  }

  function renderFilterGroup(parent, group) {
    const wrap = parent.createDiv();
    wrap.style.border = "1px solid var(--background-modifier-border)";
    wrap.style.borderRadius = "8px";
    wrap.style.padding = "0.75em";

    const headingRow = wrap.createDiv();
    headingRow.style.display = "flex";
    headingRow.style.alignItems = "center";
    headingRow.style.gap = "0.5em";
    headingRow.style.marginBottom = "0.6em";

    const headingToggle = headingRow.createEl("input", { type: "checkbox" });
    setTriState(headingToggle, group.selected.size, group.values.length);

    headingToggle.onchange = async () => {
      group.selected.clear();

      if (headingToggle.checked) {
        group.values.forEach(value => group.selected.add(value));
      }

      await saveCurrentState({ quiet: true, action: "filter" });
      render();
    };

    headingRow.createEl("strong", { text: group.title });

    const countText = headingRow.createEl("span");
    countText.style.opacity = "0.75";
    countText.setText(`(${group.selected.size}/${group.values.length})`);

    const list = wrap.createDiv();

    for (const value of group.values) {
      const label = list.createEl("label");
      label.style.display = "flex";
      label.style.alignItems = "center";
      label.style.gap = "0.5em";
      label.style.marginBottom = "0.25em";

      const checkbox = label.createEl("input", { type: "checkbox" });
      checkbox.checked = group.selected.has(value);

      checkbox.onchange = async () => {
        if (checkbox.checked) group.selected.add(value);
        else group.selected.delete(value);

        await saveCurrentState({ quiet: true, action: "filter" });
        render();
      };

      label.createEl("span", {
        text: `${value} (${model.valueCounts[group.key].get(value) ?? 0})`
      });
    }
  }

  function renderResultsTable(parent, displayedRows) {
    const tableWrap = parent.createDiv();
    tableWrap.style.overflowX = "auto";

    const table = tableWrap.createEl("table");
    table.classList.add("dataview", "table-view-table");
    table.style.width = "100%";

    const thead = table.createEl("thead");
    const headRow = thead.createEl("tr");

    headRow.createEl("th", { text: "" });

    for (const column of columns) {
      headRow.createEl("th", { text: column.title ?? "" });
    }

    const tbody = table.createEl("tbody");
    const api = getApi();

    for (const row of displayedRows) {
      const tr = tbody.createEl("tr");

      const selectCell = tr.createEl("td");
      const selectBox = selectCell.createEl("input", { type: "checkbox" });
      selectBox.checked = model.selectedKeys.has(model.getRowKey(row));

      selectBox.onchange = async () => {
        const key = model.getRowKey(row);

        if (selectBox.checked) model.selectedKeys.add(key);
        else model.selectedKeys.delete(key);

        await saveCurrentState({ quiet: true, action: "selection" });
        render();
      };

      for (const column of columns) {
        const cell = tr.createEl("td");

        if (typeof column.render === "function") {
          column.render(cell, row, api);
        } else if (typeof column.value === "function") {
          cell.setText(String(column.value(row) ?? ""));
        } else if (typeof column.key === "string") {
          cell.setText(String(row[column.key] ?? ""));
        }
      }
    }
  }

  function render() {
    const root = dv.container;
    root.innerHTML = "";

    const displayedRows = model.getDisplayedRows();
    const selectedDisplayedCount = model.getSelectedDisplayedCount(displayedRows);
    const selectedRows = model.getSelectedRows();

    publishSelectionBridge();

    renderTopBlock(root, selectedRows, displayedRows, selectedDisplayedCount);

    if (model.filterGroups.length > 0) {
      const filterWrap = root.createDiv();
      filterWrap.style.display = "grid";
      filterWrap.style.gridTemplateColumns = "repeat(auto-fit, minmax(220px, 1fr))";
      filterWrap.style.gap = "1em";
      filterWrap.style.marginBottom = "1em";

      for (const group of model.filterGroups) {
        renderFilterGroup(filterWrap, group);
      }
    }

    if (displayedRows.length === 0) {
      root.createEl("p", { text: options.noMatchesMessage });
      return;
    }

    if (typeof options.renderResults === "function") {
      options.renderResults(root, displayedRows, getApi());
    } else {
      renderResultsTable(root, displayedRows);
    }
  }

  const initialState = await stateStore.read();

  if (initialState) {
    const loaded = applySavedState(initialState);
    debugLog("initial state loaded", loaded);
  }

  installStateReloadHooks();
  render();

  return getApi();
}

module.exports = {
  renderSelectionQuery
};
