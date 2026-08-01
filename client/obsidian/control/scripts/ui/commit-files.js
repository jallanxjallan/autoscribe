"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const runtimeApp = globalThis.app;
const controlVaultRoot = runtimeApp.vault.adapter.getBasePath?.() || runtimeApp.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const path = require("node:path");
const { callFeeder } = loadControl("scripts/lib/feeder-ipc.js");
const { readClipboardSelection } = loadControl("scripts/lib/clipboard-selection.js");

function element(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "className") node.className = value;
    else if (key === "title") node.title = value;
    else if (key === "disabled") node.disabled = Boolean(value);
    else node[key] = value;
  }
  if (text !== null) node.textContent = text;
  return node;
}

function clear(node) {
  node.replaceChildren();
}

function text(value, fallback = "—") {
  const result = String(value ?? "").trim();
  return result || fallback;
}

function displayTitle(item) {
  return text(item.title, path.basename(item.path || "") || item.slug || "Untitled");
}

function shortCommit(commit) {
  if (!commit?.hash) return "—";
  const subject = String(commit.subject || "").trim();
  return `${String(commit.hash).slice(0, 8)}${subject ? ` · ${subject}` : ""}`;
}

function itemProblem(item) {
  return String(item.error || item.problem || item.reason || "").trim();
}

function itemState(item) {
  return String(item.repo_state || item.git_state || item.worktree?.label || "unknown").trim() || "unknown";
}

function isCommittable(item) {
  if (item.committable === false) return false;
  if (itemProblem(item)) return false;
  if (!String(item.path || "").trim()) return false;
  return !["missing", "outside repository", "ambiguous", "unknown"].includes(itemState(item).toLowerCase());
}

function normalizedResponse(result, parsed) {
  const items = Array.isArray(result?.items)
    ? result.items
    : Array.isArray(result?.files)
      ? result.files
      : [];

  if (!items.length && parsed.length) {
    throw new Error("Feeder returned no resolved file rows.");
  }

  return {
    items: items.map((item, index) => ({
      ...parsed[index],
      ...item,
      index: Number(item.index || parsed[index]?.index || index + 1),
      source_row: Number(item.source_row || parsed[index]?.source_row || index + 1),
    })),
    summary: result?.summary || {},
  };
}

async function renderCommitFiles({ app, container }) {
  clear(container);

  const state = {
    loading: false,
    committing: false,
    parsed: [],
    items: [],
    summary: {},
    error: "",
    commitType: "version",
  };

  const toolbar = element("div", { className: "commit-files-toolbar" });
  toolbar.style.display = "flex";
  toolbar.style.gap = "0.5rem";
  toolbar.style.alignItems = "center";
  toolbar.style.flexWrap = "wrap";

  const refreshButton = element("button", {}, "Refresh selection");
  const status = element("span", { className: "commit-files-status" }, "No selection loaded.");
  toolbar.append(refreshButton, status);

  const tableHost = element("div", { className: "commit-files-table-host" });
  const commitBox = element("div", { className: "commit-files-commit-box" });
  commitBox.style.display = "grid";
  commitBox.style.gap = "0.75rem";
  commitBox.style.marginTop = "1rem";

  const description = element("textarea", {
    placeholder: "Describe this commit",
    rows: 4,
  });
  description.style.width = "100%";

  const typeBox = element("div", { className: "commit-files-types" });
  typeBox.style.display = "grid";
  typeBox.style.gridTemplateColumns = "repeat(2, minmax(0, 1fr))";
  typeBox.style.gap = "0.75rem";

  for (const [value, label, detail] of [
    ["version", "Version", 'Tag commit as version; set file state to "versioned"'],
    ["lock", "Lock", 'Tag commit as lock; set file state to "locked"'],
  ]) {
    const choice = element("label", { className: "commit-files-type" });
    choice.style.display = "flex";
    choice.style.gap = "0.65rem";
    choice.style.padding = "0.75rem";
    choice.style.border = "1px solid var(--background-modifier-border)";
    choice.style.borderRadius = "var(--radius-m)";
    choice.style.cursor = "pointer";

    const radio = element("input", {
      type: "radio",
      name: "commit-files-type",
      value,
      checked: state.commitType === value,
    });
    radio.onchange = () => {
      if (radio.checked) state.commitType = value;
    };

    const copy = element("span");
    copy.style.display = "grid";
    copy.style.gap = "0.2rem";
    copy.append(element("strong", {}, label), element("small", {}, detail));
    choice.append(radio, copy);
    typeBox.append(choice);
  }

  const commitButton = element("button", { className: "mod-cta" }, "Commit files");
  commitBox.append(description, typeBox, commitButton);
  container.append(toolbar, tableHost, commitBox);

  function updateControls() {
    const valid = state.items.filter(isCommittable);
    const blocked = state.items.length - valid.length;
    refreshButton.disabled = state.loading || state.committing;
    commitButton.disabled = state.loading || state.committing || !valid.length || blocked > 0;
    description.disabled = state.loading || state.committing;
    for (const radio of typeBox.querySelectorAll('input[type="radio"]')) {
      radio.disabled = state.loading || state.committing;
    }

    if (state.loading) status.textContent = "Loading clipboard selection…";
    else if (state.committing) status.textContent = "Committing files…";
    else if (state.error) status.textContent = state.error;
    else if (!state.items.length) status.textContent = "No selection loaded.";
    else status.textContent = `${state.items.length} row(s), ${valid.length} committable${blocked ? `, ${blocked} blocked` : ""}.`;
  }

  function openFile(item) {
    if (!item.path) return;
    app.workspace.openLinkText(item.path, "", false);
  }

  function renderTable() {
    clear(tableHost);
    if (!state.items.length) return;

    const table = element("table", { className: "commit-files-table" });
    table.style.width = "100%";
    const head = element("tr");
    for (const label of ["#", "File", "Path", "Slug", "State", "Git state", "Latest commit", "Problem"]) {
      head.append(element("th", {}, label));
    }
    table.append(head);

    for (const item of state.items) {
      const row = element("tr");
      if (!isCommittable(item)) row.classList.add("commit-files-blocked");

      const titleCell = element("td");
      if (item.path) {
        const link = element("a", { href: item.path }, displayTitle(item));
        link.onclick = (event) => {
          event.preventDefault();
          openFile(item);
        };
        titleCell.append(link);
      } else titleCell.textContent = displayTitle(item);

      row.append(
        element("td", {}, String(item.index || "")),
        titleCell,
        element("td", {}, text(item.path)),
        element("td", {}, text(item.slug)),
        element("td", {}, text(item.state)),
        element("td", {}, itemState(item)),
        element("td", {}, shortCommit(item.latest_commit || item.user_commit || item.commit)),
        element("td", {}, text(itemProblem(item))),
      );
      table.append(row);
    }

    tableHost.append(table);
  }

  async function refreshSelection() {
    state.loading = true;
    state.error = "";
    updateControls();

    try {
      const parsed = await readClipboardSelection(app);
      const result = callFeeder(app, "git.resolve_selection", { items: parsed });
      const normalized = normalizedResponse(result, parsed);
      state.parsed = parsed;
      state.items = normalized.items;
      state.summary = normalized.summary;
      renderTable();
    } catch (error) {
      console.error("Commit Files refresh failed:", error);
      state.parsed = [];
      state.items = [];
      state.summary = {};
      state.error = `Refresh failed: ${error.message}`;
      renderTable();
      new Notice(state.error, 10000);
    } finally {
      state.loading = false;
      updateControls();
    }
  }

  function commitFiles() {
    state.error = "";
    const message = description.value.trim();
    const items = state.items;
    const blocked = items.filter((item) => !isCommittable(item));
    const commitType = state.commitType;
    const fileState = commitType === "lock" ? "locked" : "versioned";

    try {
      if (!items.length) throw new Error("The selection is empty.");
      if (blocked.length) throw new Error("Resolve every blocked row before committing.");
      if (!message) throw new Error("Enter a commit description.");

      state.committing = true;
      updateControls();

      const result = callFeeder(app, "git.commit_selection", {
        message,
        commit_type: commitType,
        tag_type: commitType,
        state: fileState,
        items: items.map((item) => ({
          index: item.index,
          source_row: item.source_row,
          path: item.path,
          slug: item.slug || "",
          title: item.title || "",
        })),
      });

      const hash = String(result?.commit?.hash || result?.commit || "").slice(0, 8) || "unknown";
      const count = Number(result?.count || result?.files?.length || items.length);
      const tag = String(result?.tag || result?.commit_tag || "").trim();
      description.value = "";
      new Notice(`Committed ${count} file(s) as ${commitType}: ${hash}${tag ? ` · ${tag}` : ""}`);
      refreshSelection();
    } catch (error) {
      console.error("Commit Files commit failed:", error);
      state.error = `Commit failed: ${error.message}`;
      new Notice(state.error, 10000);
    } finally {
      state.committing = false;
      updateControls();
    }
  }

  refreshButton.onclick = refreshSelection;
  commitButton.onclick = commitFiles;

  updateControls();
  await refreshSelection();
}


module.exports = { renderCommitFiles };
