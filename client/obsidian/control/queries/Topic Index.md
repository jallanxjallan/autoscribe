```dataviewjs
const SOURCE = '"topics"';
const USE_EXACT_TAGS = true; 
// true  = use file.etags, exact tags only
// false = use file.tags, including parent tags

const UNTAGGED_KEY = "__untagged__";
const UNTAGGED_LABEL = "Untagged";

const stateKey = `topics-tag-index:${dv.current().file.path}`;

const pages = dv.pages(SOURCE)
  .sort(p => p.file.path, "asc")
  .array();

function getTags(page) {
  const rawTags = USE_EXACT_TAGS
    ? (page.file.etags ?? page.file.tags ?? [])
    : (page.file.tags ?? []);

  return [...new Set(Array.from(rawTags).map(String))]
    .sort((a, b) => a.localeCompare(b));
}

const byTag = new Map();

for (const page of pages) {
  const tags = getTags(page);

  if (tags.length === 0) {
    if (!byTag.has(UNTAGGED_KEY)) byTag.set(UNTAGGED_KEY, []);
    byTag.get(UNTAGGED_KEY).push(page);
    continue;
  }

  for (const tag of tags) {
    if (!byTag.has(tag)) byTag.set(tag, []);
    byTag.get(tag).push(page);
  }
}

const tagEntries = [...byTag.entries()]
  .sort(([a], [b]) => {
    if (a === UNTAGGED_KEY) return 1;
    if (b === UNTAGGED_KEY) return -1;
    return a.localeCompare(b);
  });

function displayTag(tag) {
  return tag === UNTAGGED_KEY ? UNTAGGED_LABEL : tag;
}

function loadSelectedTags() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(stateKey) ?? "null");
    if (!Array.isArray(saved)) throw new Error("No saved state");

    const validTags = new Set(tagEntries.map(([tag]) => tag));
    const selected = new Set(saved.filter(tag => validTags.has(tag)));

    return selected.size ? selected : new Set(tagEntries.map(([tag]) => tag));
  } catch {
    return new Set(tagEntries.map(([tag]) => tag));
  }
}

function saveSelectedTags() {
  sessionStorage.setItem(stateKey, JSON.stringify([...selectedTags]));
}

function makeFileLink(page) {
  const link = document.createElement("a");
  link.textContent = page.file.name;
  link.href = page.file.path;
  link.className = "internal-link";
  link.setAttribute("data-href", page.file.path);

  link.addEventListener("click", event => {
    event.preventDefault();
    app.workspace.openLinkText(
      page.file.path,
      dv.current().file.path,
      event.ctrlKey || event.metaKey
    );
  });

  return link;
}

let selectedTags = loadSelectedTags();

const root = dv.container;
root.innerHTML = "";

const controls = document.createElement("div");
controls.style.border = "1px solid var(--background-modifier-border)";
controls.style.borderRadius = "8px";
controls.style.padding = "0.75rem";
controls.style.marginBottom = "1rem";

const title = document.createElement("h3");
title.textContent = "Topic tags";
title.style.marginTop = "0";
controls.appendChild(title);

const buttonRow = document.createElement("div");
buttonRow.style.display = "flex";
buttonRow.style.gap = "0.5rem";
buttonRow.style.marginBottom = "0.75rem";
buttonRow.style.flexWrap = "wrap";

function makeButton(label, onClick) {
  const button = document.createElement("button");
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

const grid = document.createElement("div");
grid.style.display = "grid";
grid.style.gridTemplateColumns = "repeat(auto-fill, minmax(220px, 1fr))";
grid.style.gap = "0.35rem 1rem";

const resultContainer = document.createElement("div");

const checkboxes = new Map();

function renderResults() {
  resultContainer.innerHTML = "";

  const selectedEntries = tagEntries.filter(([tag]) => selectedTags.has(tag));

  if (selectedEntries.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No tags selected.";
    empty.style.fontStyle = "italic";
    resultContainer.appendChild(empty);
    return;
  }

  for (const [tag, files] of selectedEntries) {
    const heading = document.createElement("h3");
    heading.textContent = `${displayTag(tag)} (${files.length})`;
    resultContainer.appendChild(heading);

    const list = document.createElement("ul");

    for (const page of files) {
      const item = document.createElement("li");
      item.appendChild(makeFileLink(page));
      list.appendChild(item);
    }

    resultContainer.appendChild(list);
  }
}

function syncCheckboxes() {
  for (const [tag, checkbox] of checkboxes.entries()) {
    checkbox.checked = selectedTags.has(tag);
  }
}

buttonRow.appendChild(makeButton("All", () => {
  selectedTags = new Set(tagEntries.map(([tag]) => tag));
  saveSelectedTags();
  syncCheckboxes();
  renderResults();
}));

buttonRow.appendChild(makeButton("None", () => {
  selectedTags = new Set();
  saveSelectedTags();
  syncCheckboxes();
  renderResults();
}));

buttonRow.appendChild(makeButton("Reset", () => {
  sessionStorage.removeItem(stateKey);
  selectedTags = new Set(tagEntries.map(([tag]) => tag));
  syncCheckboxes();
  renderResults();
}));

controls.appendChild(buttonRow);

for (const [tag, files] of tagEntries) {
  const label = document.createElement("label");
  label.style.display = "flex";
  label.style.alignItems = "center";
  label.style.gap = "0.35rem";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = selectedTags.has(tag);

  checkbox.addEventListener("change", () => {
    if (checkbox.checked) {
      selectedTags.add(tag);
    } else {
      selectedTags.delete(tag);
    }

    saveSelectedTags();
    renderResults();
  });

  checkboxes.set(tag, checkbox);

  const text = document.createElement("span");
  text.textContent = `${displayTag(tag)} (${files.length})`;

  label.appendChild(checkbox);
  label.appendChild(text);
  grid.appendChild(label);
}

controls.appendChild(grid);
root.appendChild(controls);
root.appendChild(resultContainer);

renderResults();
```