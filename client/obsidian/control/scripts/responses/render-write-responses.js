"use strict";

const { spawnSync } = require("node:child_process");
const { callFeeder, vaultRoot } = require("../lib/feeder-ipc");
const { buildSlugPathMap } = require("../lib/rg");
const { createInternalLink } = require("../lib/internal-link");

function el(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "className") node.className = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  if (text !== null) node.textContent = text;
  return node;
}

function gitStates(root) {
  const result = spawnSync("git", ["status", "--porcelain=v1", "-z", "--untracked-files=all"], {
    cwd: root,
    encoding: "utf8",
    shell: false,
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(String(result.stderr || result.stdout || `git exited ${result.status}`).trim());
  }

  const states = new Map();
  const entries = String(result.stdout || "").split("\0").filter(Boolean);
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const status = entry.slice(0, 2);
    const path = entry.slice(3).trim().replaceAll("\\", "/");
    if (path) states.set(path, status);
    if (status.includes("R") || status.includes("C")) index += 1;
  }
  return states;
}

function shortIdentity(value) {
  const text = String(value || "");
  return text.length <= 18 ? text : `${text.slice(0, 8)}…${text.slice(-7)}`;
}

function candidateRows({ responses, bySlug, duplicates, states }) {
  const matched = [];
  const unmatched = [];
  const duplicate = [];

  for (const response of responses) {
    const slug = String(response.prompt_slug || "").trim();
    if (duplicates.has(slug)) {
      duplicate.push(response);
      continue;
    }
    const target = bySlug.get(slug);
    if (!target) {
      unmatched.push(response);
      continue;
    }
    const gitStatus = states.get(target.path) || "";
    matched.push({
      ...response,
      path: target.path,
      line_number: target.lineNumber,
      git_status: gitStatus,
      dirty: Boolean(gitStatus),
    });
  }

  matched.sort((a, b) => a.path.localeCompare(b.path));
  unmatched.sort((a, b) => a.prompt_slug.localeCompare(b.prompt_slug));
  duplicate.sort((a, b) => a.prompt_slug.localeCompare(b.prompt_slug));
  return { matched, unmatched, duplicate };
}

function renderTable({ app, parent, title, items, selected, defaultChecked = false }) {
  parent.appendChild(el("h2", {}, title));
  if (!items.length) {
    parent.appendChild(el("p", {}, "None."));
    return [];
  }

  const toolbar = el("div", { style: "display:flex;gap:.5rem;align-items:center;margin:.5rem 0;flex-wrap:wrap;" });
  const selectAll = el("button", {}, "Select all");
  const clearAll = el("button", {}, "Clear all");
  const count = el("span", {}, "");
  toolbar.append(selectAll, clearAll, count);
  parent.appendChild(toolbar);

  const table = el("table", { style: "width:100%;" });
  const head = el("tr");
  for (const label of ["", "File", "Slug", "Git", "Call", "Response"]) {
    head.appendChild(el("th", {}, label));
  }
  table.appendChild(head);

  const rows = items.map((item) => {
    const tr = el("tr");
    const checkbox = el("input", { type: "checkbox", checked: defaultChecked });
    if (defaultChecked) selected.add(item.result_identity);
    const checkCell = el("td");
    checkCell.appendChild(checkbox);
    const fileCell = el("td");
    createInternalLink(fileCell, app, item.path, item.path);
    tr.append(
      checkCell,
      fileCell,
      el("td", {}, item.prompt_slug),
      el("td", {}, item.git_status || "clean"),
      el("td", {}, shortIdentity(item.call_identity)),
      el("td", {}, shortIdentity(item.result_identity)),
    );
    table.appendChild(tr);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selected.add(item.result_identity);
      else selected.delete(item.result_identity);
      updateCount();
    });
    return { item, checkbox };
  });

  function updateCount() {
    count.textContent = `${rows.filter((row) => row.checkbox.checked).length} of ${rows.length} selected`;
  }
  selectAll.onclick = () => {
    for (const row of rows) {
      row.checkbox.checked = true;
      selected.add(row.item.result_identity);
    }
    updateCount();
  };
  clearAll.onclick = () => {
    for (const row of rows) {
      row.checkbox.checked = false;
      selected.delete(row.item.result_identity);
    }
    updateCount();
  };
  updateCount();
  parent.appendChild(table);
  return rows;
}

async function renderWriteResponses({ app, container }) {
  const root = vaultRoot(app);
  const state = {
    cleanSelected: new Set(),
    dirtySelected: new Set(),
    candidates: null,
  };

  async function refresh() {
    container.replaceChildren(el("p", {}, "Loading pending responses…"));
    try {
      const responses = callFeeder(app, "responses.pending");
      if (!Array.isArray(responses)) throw new Error("responses.pending returned no response list");

      const { bySlug, duplicates } = buildSlugPathMap({ root });
      const states = gitStates(root);
      const candidates = candidateRows({ responses, bySlug, duplicates, states });
      state.candidates = candidates;
      state.cleanSelected.clear();
      state.dirtySelected.clear();
      render();
    } catch (error) {
      console.error(error);
      container.replaceChildren(el("p", {}, `Write Responses failed: ${error.message}`));
      new Notice(`Write Responses failed: ${error.message}`, 10000);
    }
  }

  function chosen(items, selected) {
    return items.filter((item) => selected.has(item.result_identity));
  }

  function write(items, allowDirty) {
    if (!items.length) {
      new Notice("No responses selected.");
      return;
    }
    if (allowDirty) {
      const paths = items.map((item) => `• ${item.path}`).join("\n");
      const accepted = window.confirm(
        `These files already contain uncommitted changes. Writeback will replace their bodies and may discard those edits.\n\n${paths}\n\nAre you sure?`,
      );
      if (!accepted) return;
    }

    try {
      const result = callFeeder(app, "responses.write", {
        items,
        allow_dirty: allowDirty,
      });
      const changed = result.filter((item) => item.changed).length;
      new Notice(`Wrote ${result.length} response(s); ${changed} file(s) changed.`);
      refresh();
    } catch (error) {
      console.error(error);
      new Notice(`Writeback failed: ${error.message}`, 10000);
    }
  }

  function renderExceptions(parent, title, items, reason) {
    if (!items.length) return;
    parent.appendChild(el("h2", {}, title));
    parent.appendChild(el("p", {}, reason));
    const table = el("table");
    const head = el("tr");
    head.append(el("th", {}, "Slug"), el("th", {}, "Call"), el("th", {}, "Response"));
    table.appendChild(head);
    for (const item of items) {
      const row = el("tr");
      row.append(
        el("td", {}, item.prompt_slug),
        el("td", {}, shortIdentity(item.call_identity)),
        el("td", {}, shortIdentity(item.result_identity)),
      );
      table.appendChild(row);
    }
    parent.appendChild(table);
  }

  function render() {
    const { matched, unmatched, duplicate } = state.candidates;
    const clean = matched.filter((item) => !item.dirty);
    const dirty = matched.filter((item) => item.dirty);

    container.replaceChildren();
    const header = el("div", { style: "display:flex;gap:.75rem;align-items:center;flex-wrap:wrap;" });
    header.append(
      el("button", { onclick: refresh }, "Refresh"),
      el("span", {}, `${matched.length} matching response(s); ${unmatched.length} unmatched; ${duplicate.length} duplicate-slug response(s)`),
    );
    container.appendChild(header);

    renderTable({
      app,
      parent: container,
      title: "Clean files",
      items: clean,
      selected: state.cleanSelected,
      defaultChecked: true,
    });
    const cleanButton = el("button", {
      onclick: () => write(chosen(clean, state.cleanSelected), false),
      style: "margin-top:.75rem;",
    }, "Write selected clean responses");
    cleanButton.disabled = clean.length === 0;
    container.appendChild(cleanButton);

    renderTable({
      app,
      parent: container,
      title: "Dirty files",
      items: dirty,
      selected: state.dirtySelected,
      defaultChecked: false,
    });
    if (dirty.length) {
      container.appendChild(el("p", {}, "Dirty files are never selected automatically. Writing them requires a separate confirmation."));
    }
    const dirtyButton = el("button", {
      onclick: () => write(chosen(dirty, state.dirtySelected), true),
      style: "margin-top:.75rem;",
    }, "Write selected dirty responses…");
    dirtyButton.disabled = dirty.length === 0;
    container.appendChild(dirtyButton);

    renderExceptions(container, "Unmatched response slugs", unmatched, "No Markdown file in the active vault has these slugs.");
    renderExceptions(container, "Duplicate vault slugs", duplicate, "Writeback is disabled because each slug must resolve to exactly one file.");
  }

  await refresh();
}

module.exports = { renderWriteResponses, candidateRows, gitStates };
