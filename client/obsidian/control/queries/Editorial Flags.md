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
      .map(value => String(value).trim())
      .filter(Boolean);

    return values.length ? [...new Set(values)] : [MISSING];
  }

  const text = String(value).trim();
  return text ? [text] : [MISSING];
}

function truncateAtWord(text, limit = PREVIEW_LIMIT) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;

  const slice = normalized.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");

  if (lastSpace > 0) {
    return slice.slice(0, lastSpace).trimEnd() + "…";
  }

  return normalized.slice(0, limit - 1).trimEnd() + "…";
}

function extractCalloutFirstLine(line) {
  const match = line.match(/^\s*>\s*(\\?\[!.*)$/i);
  if (!match) return null;

  const text = match[1]
    .replace(/\\/g, "")
    .replace(/[\[\]]/g, " ")
    .replace(/!\s*/, "")
    .replace(/\s+/g, " ")
    .trim();

  return text ? truncateAtWord(text) : null;
}

function extractHighlights(line) {
  return [...line.matchAll(/==(.+?)==/g)]
    .map(match => match[1].trim())
    .filter(Boolean)
    .map(text => truncateAtWord(text));
}

function tkPreview(line) {
  if (!/\*\*TK\*\*/i.test(line)) return null;
  return truncateAtWord(line.replace(/\*\*TK\*\*/gi, "TK"));
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

  let inFrontmatter = lines[0]?.trim() === "---";
  let inFence = false;

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const trimmed = line.trim();

    if (inFrontmatter) {
      if (index > 0 && trimmed === "---") inFrontmatter = false;
      continue;
    }

    if (/^(```|~~~)/.test(trimmed)) {
      inFence = !inFence;
      continue;
    }

    if (inFence) continue;

    const base = {
      path: file.path,
      line: index + 1,
      stageValues,
      statusValues
    };

    const callout = extractCalloutFirstLine(line);
    if (callout) {
      rows.push({ ...base, type: "Callout", text: callout });
    }

    const tk = tkPreview(line);
    if (tk) {
      rows.push({ ...base, type: "TK", text: tk });
    }

    for (const highlight of extractHighlights(line)) {
      rows.push({ ...base, type: "Highlight", text: highlight });
    }
  }
}

if (rows.length === 0) {
  dv.paragraph("No editorial flags found.");
  return;
}

const allStages = [...new Set(rows.flatMap(row => row.stageValues))].sort((a, b) =>
  a.localeCompare(b, undefined, { sensitivity: "base" })
);

const allStatuses = [...new Set(rows.flatMap(row => row.statusValues))].sort((a, b) =>
  a.localeCompare(b, undefined, { sensitivity: "base" })
);

const allTypes = [...new Set(rows.map(row => row.type))].sort((a, b) =>
  a.localeCompare(b, undefined, { sensitivity: "base" })
);

const selectedStages = new Set(allStages);
const selectedStatuses = new Set(allStatuses);
const selectedTypes = new Set(allTypes);

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

  renderChecklist(controls, "Type", allTypes, selectedTypes);
  renderChecklist(controls, "Stage", allStages, selectedStages);
  renderChecklist(controls, "Status", allStatuses, selectedStatuses);

  const filtered = rows.filter(row =>
    selectedTypes.has(row.type) &&
    matchesAny(row.stageValues, selectedStages) &&
    matchesAny(row.statusValues, selectedStatuses)
  );

  root.createEl("p", {
    text: `${filtered.length} matching editorial flag${filtered.length === 1 ? "" : "s"}`
  });

  if (filtered.length === 0) {
    root.createEl("p", { text: "No matching editorial flags." });
    return;
  }

  const sortedFiltered = [...filtered].sort((a, b) =>
    a.path.localeCompare(b.path, undefined, { sensitivity: "base" }) ||
    a.line - b.line ||
    a.type.localeCompare(b.type, undefined, { sensitivity: "base" })
  );

  dv.table(
    ["Note", "Type", "Text"],
    sortedFiltered.map(row => [
      dv.fileLink(row.path),
      row.type,
      row.text
    ])
  );
}

render();
```
