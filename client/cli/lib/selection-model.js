function normalizeFilterValue(value) {
  return String(value ?? "").trim();
}

function sortText(values) {
  return [...values]
    .map(normalizeFilterValue)
    .sort((a, b) => a.localeCompare(b, undefined, {
      numeric: true,
      sensitivity: "base"
    }));
}

function countValues(rows, key) {
  const counts = new Map();

  for (const row of rows) {
    const value = normalizeFilterValue(row[key]);
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }

  return counts;
}

function buildFilterGroups(rows, filterFields) {
  return filterFields.map(field => {
    const values = sortText(new Set(rows.map(row => row[field.key])));

    return {
      key: field.key,
      title: field.title,
      values,
      selected: new Set(values)
    };
  });
}

function buildValueCounts(rows, filterGroups) {
  return Object.fromEntries(
    filterGroups.map(group => [group.key, countValues(rows, group.key)])
  );
}

function createSelectionModel({
  rows,
  filterFields = [],
  sortModes = [],
  defaultSortMode = "slug",
  selectionKey = "slug",
  sortRows = null
}) {
  if (!Array.isArray(rows)) throw new Error("createSelectionModel requires rows.");

  const filterGroups = buildFilterGroups(rows, filterFields);
  const valueCounts = buildValueCounts(rows, filterGroups);
  const selectedKeys = new Set();
  let sortMode = defaultSortMode;

  function getRowKey(row) {
    return row[selectionKey];
  }

  function getSelectedRows() {
    return rows.filter(row => selectedKeys.has(getRowKey(row)));
  }

  function rowMatchesFilters(row) {
    return filterGroups.every(group =>
      group.selected.has(normalizeFilterValue(row[group.key]))
    );
  }

  function getFilteredRows() {
    return rows.filter(rowMatchesFilters);
  }

  function getDisplayedRows() {
    const filteredRows = getFilteredRows();
    return typeof sortRows === "function" ? sortRows(filteredRows, sortMode) : [...filteredRows];
  }

  function getSelectedDisplayedCount(displayedRows = getDisplayedRows()) {
    return displayedRows.filter(row => selectedKeys.has(getRowKey(row))).length;
  }

  function reset() {
    for (const group of filterGroups) {
      group.selected.clear();
      group.values.forEach(value => group.selected.add(value));
    }

    selectedKeys.clear();
    sortMode = defaultSortMode;
  }

  function setSortMode(value) {
    sortMode = value;
  }

  function getSortMode() {
    return sortMode;
  }

  function getValidSortModes() {
    return new Set(sortModes.map(([value]) => value));
  }

  function getValidSelectionKeys() {
    return new Set(rows.map(getRowKey));
  }

  return {
    rows,
    filterGroups,
    valueCounts,
    selectedKeys,
    selectionKey,
    sortModes,
    defaultSortMode,
    getRowKey,
    getSelectedRows,
    getFilteredRows,
    getDisplayedRows,
    getSelectedDisplayedCount,
    rowMatchesFilters,
    reset,
    setSortMode,
    getSortMode,
    getValidSortModes,
    getValidSelectionKeys
  };
}

module.exports = {
  normalizeFilterValue,
  sortText,
  countValues,
  buildFilterGroups,
  buildValueCounts,
  createSelectionModel
};