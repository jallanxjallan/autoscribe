
```dataviewjs
const rows = [];
const MISSING = "—";
const PREVIEW_LIMIT = 60;

function isExcludedFolder(path) {
  return path
    .split("/")
    .slice(0, -1)
    .some(part => part.startsWith("_"));
}

function normalizeMetaValues(value) {
  if (value == null) return [MISSING];

  if (Array.isArray(value)) {
    const values = value
      .flatMap(normalizeMetaValues)
      .map(v => String(v).trim())
      .filter(Boolean);

    return values.length ? [...new Set(values)] : [MISSING];
  }

  const text = String(value).trim();
  return text ? [text] : [MISSING];
}

function truncateAtWord(text, limit = PREVIEW_LIMIT) {
  if (text.length <= limit) return text;

  const slice = text.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");

  if (lastSpace > 0) {
    return slice.slice(0, lastSpace).trimEnd() + "…";
  }

  return text.slice(0, limit - 1).trimEnd() + "…";
}

function extractCalloutFirstLine(line) {
  const match = line.match(/^\s*>\s*(\\?\[!.*)$/i);
  if (!match) return null;

  let text = match[1];

  text = text.replace(/\\/g, "");
  text = text.replace(/[\[\]]/g, " ");
  text = text.replace(/!\s*/, "");
  text = text.replace(/\s+/g, " ").trim();

  if (!text) return null;

  return truncateAtWord(text, PREVIEW_LIMIT);
}

for (const file of app.vault.getMarkdownFiles()
  .filter(file => !isExcludedFolder(file.path))
  .sort((a, b) => a.path.localeCompare(b.path))) {

  const cache = app.metadataCache.getFileCache(file);
  const frontmatter = cache?.frontmatter ?? {};

  const stageValues = normalizeMetaValues(frontmatter.stage);
  const statusValues = normalizeMetaValues(frontmatter.status);

  const text = await app.vault.cachedRead(file);
  const lines = text.split(/\r?\n/);

  for (const line of lines) {
    const firstLine = extractCalloutFirstLine(line);
    if (firstLine) {
      rows.push({
        path: file.path,
        firstLine,
        stageValues,
        statusValues
      });
    }
  }
}

if (rows.length === 0) {
  dv.paragraph("No callouts found.");
  return;
}

const allStages = [...new Set(rows.flatMap(row => row.stageValues))].sort((a, b) =>
  a.localeCompare(b, undefined, { sensitivity: "base" })
);

const allStatuses = [...new Set(rows.flatMap(row => row.statusValues))].sort((a, b) =>
  a.localeCompare(b, undefined, { sensitivity: "base" })
);

const selectedStages = new Set(allStages);
const selectedStatuses = new Set(allStatuses);

function matchesAny(values, selected) {
  return values.some(value => selected.has(value));
}

function renderChecklist(container, title, values, selected) {
  const section = container.createDiv();
  section.style.marginTop = "0.75em";

  section.createEl("strong", { text: title });

  const buttons = section.createDiv();
  buttons.style.marginTop = "0.4em";
  buttons.style.marginBottom = "0.4em";

  const selectAllBtn = buttons.createEl("button", { text: "Select all" });
  selectAllBtn.style.marginRight = "0.5em";
  selectAllBtn.onclick = () => {
    selected.clear();
    values.forEach(value => selected.add(value));
    render();
  };

  const clearAllBtn = buttons.createEl("button", { text: "Clear all" });
  clearAllBtn.onclick = () => {
    selected.clear();
    render();
  };

  section.createEl("div", {
    text: `${selected.size} of ${values.length} selected`
  });

  const checklist = section.createDiv();
  checklist.style.marginTop = "0.5em";

  for (const value of values) {
    const label = checklist.createEl("label");
    label.style.display = "block";
    label.style.marginBottom = "0.25em";

    const checkbox = label.createEl("input", { type: "checkbox" });
    checkbox.checked = selected.has(value);
    checkbox.style.marginRight = "0.5em";

    checkbox.onchange = () => {
      if (checkbox.checked) {
        selected.add(value);
      } else {
        selected.delete(value);
      }
      render();
    };

    label.appendText(value);
  }
}

function render() {
  const root = dv.container;
  root.innerHTML = "";

  const controls = root.createDiv();
  controls.style.marginBottom = "1em";

  renderChecklist(controls, "Stage", allStages, selectedStages);
  renderChecklist(controls, "Status", allStatuses, selectedStatuses);

  const filtered = rows.filter(row =>
    matchesAny(row.stageValues, selectedStages) &&
    matchesAny(row.statusValues, selectedStatuses)
  );

  root.createEl("p", {
    text: `${filtered.length} matching callout${filtered.length === 1 ? "" : "s"}`
  });

  if (filtered.length === 0) {
    root.createEl("p", { text: "No matching callouts." });
    return;
  }

  const sortedFiltered = filtered.sort((a, b) =>
  a.path.split("/").pop().localeCompare(
    b.path.split("/").pop(),
    undefined,
    { sensitivity: "base" }
  )
);

dv.table(
  ["Note", "First line"],
  sortedFiltered.map(row => [
    dv.fileLink(row.path),
    row.firstLine
  ])
);
}

render();
```