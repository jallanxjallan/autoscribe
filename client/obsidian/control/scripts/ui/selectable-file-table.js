const { setTriState } = require("../lib/dom");
const { createInternalLink } = require("../lib/internal-link");

function makeEl(parent, tag, attrs = {}, text = "") {
  const el = document.createElement(tag);

  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") {
      el.className = value;
    } else if (key === "style") {
      el.setAttribute("style", value);
    } else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      el.setAttribute(key, value);
    }
  }

  if (text) el.textContent = text;
  parent.appendChild(el);

  return el;
}

function selectedRows(rows) {
  return rows.filter((row) => row.checkbox.checked);
}

function visibleRows(rows) {
  return rows.filter((row) => row.tr.style.display !== "none");
}

function setVisibleChecked(rows, checked) {
  for (const row of visibleRows(rows)) {
    row.checkbox.checked = checked;
  }
}

function rowMatchesMode(row, mode) {
  if (!mode?.accepts) return true;
  return mode.accepts(row);
}

function applyFilter(rows, filterInput, modeSelect, modesByValue) {
  const needle = String(filterInput.value || "").toLowerCase().trim();
  const mode = modesByValue.get(modeSelect.value);

  for (const row of rows) {
    const haystack = `${row.file.path} ${row.slug}`.toLowerCase();

    const visible =
      rowMatchesMode(row, mode) &&
      (!needle || haystack.includes(needle));

    row.tr.style.display = visible ? "" : "none";
  }
}

function renderSelectableFileTable({
  app,
  container,
  files,
  getSlug,
  modes,
  defaultMode
}) {
  const modesByValue = new Map(
    modes.map((mode) => [mode.value, mode])
  );

  const controls = makeEl(container, "div", {
    style: "display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap; margin:0.75rem 0;"
  });

  makeEl(controls, "label", {}, "Show:");

  const modeSelect = makeEl(controls, "select");

  for (const mode of modes) {
    makeEl(modeSelect, "option", { value: mode.value }, mode.label);
  }

  modeSelect.value = defaultMode;

  const filterInput = makeEl(controls, "input", {
    type: "search",
    placeholder: "Filter path or slug",
    style: "min-width:18rem;"
  });

  const buttonRow = makeEl(container, "div", {
    style: "display:flex; gap:0.5rem; align-items:center; margin:0.75rem 0;"
  });

  const selectVisibleButton = makeEl(buttonRow, "button", {}, "Select visible");
  const clearVisibleButton = makeEl(buttonRow, "button", {}, "Clear visible");

  const visibleStateBox = makeEl(buttonRow, "input", {
    type: "checkbox",
    title: "Visible selection state"
  });
  visibleStateBox.disabled = true;

  const status = makeEl(buttonRow, "span", {
    style: "margin-left:0.5rem;"
  }, "");

  const table = makeEl(container, "table");
  const thead = makeEl(table, "thead");
  const headRow = makeEl(thead, "tr");

  makeEl(headRow, "th", {}, "");
  makeEl(headRow, "th", {}, "File");
  makeEl(headRow, "th", {}, "Slug");

  const tbody = makeEl(table, "tbody");

  const rows = files.map((file) => {
    const slug = getSlug(file);

    const tr = makeEl(tbody, "tr");

    const checkCell = makeEl(tr, "td");
    const checkbox = makeEl(checkCell, "input", {
      type: "checkbox"
    });

    const pathCell = makeEl(tr, "td");
    createInternalLink(pathCell, app, file.path, file.path);

    makeEl(tr, "td", {}, slug || "—");

    return {
      file,
      slug,
      tr,
      checkbox
    };
  });

  function updateStatus() {
    const displayed = visibleRows(rows);
    const selectedDisplayed = displayed.filter((row) => row.checkbox.checked);

    setTriState(visibleStateBox, selectedDisplayed.length, displayed.length);

    status.textContent =
      `${selectedRows(rows).length} selected; ${displayed.length} visible; ${rows.length} candidate(s)`;
  }

  function refresh() {
    applyFilter(rows, filterInput, modeSelect, modesByValue);
    updateStatus();
  }

  for (const row of rows) {
    row.checkbox.addEventListener("change", updateStatus);
  }

  modeSelect.addEventListener("change", refresh);
  filterInput.addEventListener("input", refresh);

  selectVisibleButton.addEventListener("click", () => {
    setVisibleChecked(rows, true);
    updateStatus();
  });

  clearVisibleButton.addEventListener("click", () => {
    setVisibleChecked(rows, false);
    updateStatus();
  });

  refresh();

  return {
    rows,
    selectedRows: () => selectedRows(rows),
    visibleRows: () => visibleRows(rows),
    refresh
  };
}

module.exports = {
  makeEl,
  renderSelectableFileTable
};