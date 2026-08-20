"use strict";

/*
 * QuickAdd macro: Vocabulary Cheatsheet
 *
 * Reads config/vocabulary.yaml at invocation time. The YAML lists remain the
 * canonical controlled vocabulary; inline comments on list entries are shown
 * as the human-readable descriptions in this modal.
 */

module.exports = async function vocabularyCheatsheet(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const fs = nodeRequire("node:fs");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const controlRoot = path.join(base, "_control");
  const configPath = path.join(controlRoot, "config", "vocabulary.yaml");
  const loaderPath = path.join(controlRoot, "scripts", "lib", "config-loader.js");

  const { loadConfig } = nodeRequire(loaderPath);
  const vocabulary = loadConfig("vocabulary");
  const source = fs.readFileSync(configPath, "utf8");
  const descriptions = parseInlineDescriptions(source);

  openVocabularyDialog(vocabulary, descriptions);
};

function parseInlineDescriptions(source) {
  const result = new Map();
  let section = null;

  for (const rawLine of String(source || "").split(/\r?\n/)) {
    const heading = rawLine.match(/^([A-Za-z][\w-]*):\s*(?:#.*)?$/);
    if (heading) {
      section = heading[1];
      continue;
    }

    if (!section) continue;

    const item = rawLine.match(/^\s{2}-\s+([^#\s][^#]*?)(?:\s+#\s*(.*))?\s*$/);
    if (!item) continue;

    const value = item[1].trim().replace(/^(["'])(.*)\1$/, "$2");
    const description = String(item[2] || "").trim();
    if (description) result.set(`${section}\0${value}`, description);
  }

  return result;
}

function titleCase(value) {
  return String(value || "")
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function openVocabularyDialog(vocabulary, descriptions) {
  const sections = Object.entries(vocabulary || {})
    .filter(([, values]) => Array.isArray(values));

  if (!sections.length) {
    new Notice("No list vocabularies found in config/vocabulary.yaml.");
    return;
  }

  let closed = false;
  const style = document.createElement("style");
  style.textContent = `
    .vocab-sheet-overlay {
      position: fixed; inset: 0; z-index: var(--layer-modal, 1000);
      display: grid; place-items: center; padding: 2rem;
      background: rgba(0, 0, 0, .45);
    }
    .vocab-sheet-dialog {
      width: min(64rem, 96vw); max-height: min(82vh, 60rem);
      display: flex; flex-direction: column; overflow: hidden;
      background: var(--background-primary); color: var(--text-normal);
      border: 1px solid var(--background-modifier-border);
      border-radius: var(--radius-l, 12px);
      box-shadow: var(--shadow-l);
    }
    .vocab-sheet-header {
      display: flex; align-items: center; gap: .75rem;
      padding: 1rem 1.1rem; border-bottom: 1px solid var(--background-modifier-border);
    }
    .vocab-sheet-header h2 { margin: 0; flex: 0 0 auto; }
    .vocab-sheet-search { flex: 1 1 auto; min-width: 10rem; }
    .vocab-sheet-close { flex: 0 0 auto; }
    .vocab-sheet-body { overflow: auto; padding: .8rem 1.1rem 1.1rem; }
    .vocab-sheet-section { border-bottom: 1px solid var(--background-modifier-border); }
    .vocab-sheet-section:last-child { border-bottom: 0; }
    .vocab-sheet-section summary {
      cursor: pointer; font-weight: 700; font-size: 1.05em; padding: .75rem .2rem;
    }
    .vocab-sheet-list { margin: 0 0 .9rem; padding: 0; list-style: none; }
    .vocab-sheet-row {
      display: grid; grid-template-columns: minmax(8rem, 12rem) 1fr;
      gap: .8rem; align-items: baseline; padding: .34rem .2rem;
    }
    .vocab-sheet-term { font-family: var(--font-monospace); font-weight: 600; }
    .vocab-sheet-description { color: var(--text-muted); }
    .vocab-sheet-empty { padding: 1rem .2rem; color: var(--text-muted); }
    @media (max-width: 620px) {
      .vocab-sheet-overlay { padding: .5rem; }
      .vocab-sheet-row { grid-template-columns: 1fr; gap: .12rem; }
    }
  `;

  const overlay = document.createElement("div");
  overlay.className = "vocab-sheet-overlay";

  const dialog = document.createElement("div");
  dialog.className = "vocab-sheet-dialog";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-label", "Vocabulary Cheatsheet");

  const header = document.createElement("div");
  header.className = "vocab-sheet-header";

  const title = document.createElement("h2");
  title.textContent = "Vocabulary";

  const search = document.createElement("input");
  search.className = "vocab-sheet-search";
  search.type = "search";
  search.placeholder = "Filter terms or definitions…";
  search.setAttribute("aria-label", "Filter vocabulary");

  const closeButton = document.createElement("button");
  closeButton.className = "vocab-sheet-close";
  closeButton.textContent = "Close";

  header.append(title, search, closeButton);

  const body = document.createElement("div");
  body.className = "vocab-sheet-body";

  const sectionNodes = [];

  for (const [sectionName, values] of sections) {
    const details = document.createElement("details");
    details.className = "vocab-sheet-section";
    details.open = sectionName === "stage" || sectionName === "status";

    const summary = document.createElement("summary");
    summary.textContent = `${titleCase(sectionName)} (${values.length})`;
    details.appendChild(summary);

    const list = document.createElement("ul");
    list.className = "vocab-sheet-list";

    const rows = [];
    for (const rawValue of values) {
      const value = String(rawValue ?? "").trim();
      if (!value) continue;

      const row = document.createElement("li");
      row.className = "vocab-sheet-row";

      const term = document.createElement("code");
      term.className = "vocab-sheet-term";
      term.textContent = value;

      const description = document.createElement("span");
      description.className = "vocab-sheet-description";
      description.textContent = descriptions.get(`${sectionName}\0${value}`) || "";

      row.append(term, description);
      list.appendChild(row);

      rows.push({
        node: row,
        haystack: `${sectionName} ${value} ${description.textContent}`.toLowerCase(),
      });
    }

    details.appendChild(list);
    body.appendChild(details);
    sectionNodes.push({ details, rows, wasOpen: details.open });
  }

  const empty = document.createElement("div");
  empty.className = "vocab-sheet-empty";
  empty.textContent = "No matching vocabulary entries.";
  empty.hidden = true;
  body.appendChild(empty);

  dialog.append(header, body);
  overlay.appendChild(dialog);
  document.head.appendChild(style);
  document.body.appendChild(overlay);

  function close() {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKeydown, true);
    style.remove();
    overlay.remove();
  }

  function onKeydown(event) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    close();
  }

  function applyFilter() {
    const query = search.value.trim().toLowerCase();
    let visibleCount = 0;

    for (const section of sectionNodes) {
      let sectionCount = 0;
      for (const row of section.rows) {
        const visible = !query || row.haystack.includes(query);
        row.node.hidden = !visible;
        if (visible) sectionCount += 1;
      }

      section.details.hidden = sectionCount === 0;
      if (query && sectionCount) section.details.open = true;
      if (!query) section.details.open = section.wasOpen;
      visibleCount += sectionCount;
    }

    empty.hidden = visibleCount !== 0;
  }

  closeButton.addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  search.addEventListener("input", applyFilter);
  document.addEventListener("keydown", onKeydown, true);

  setTimeout(() => search.focus(), 0);
}
