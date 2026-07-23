"use strict";

const { callFeeder } = require("../lib/feeder-ipc");
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

function formatDate(timestamp) {
  if (!timestamp) return "";
  return new Date(Number(timestamp) * 1000).toLocaleString();
}

async function renderWriteResponses({ app, container }) {
  const state = { candidates: [], selectedHash: "", busy: false, result: null };

  async function refresh() {
    state.busy = true;
    state.result = null;
    render();
    try {
      const candidates = callFeeder(app, "writeback.candidates", { limit: 200 });
      if (!Array.isArray(candidates)) throw new Error("writeback.candidates returned no list");
      state.candidates = candidates;
      if (!candidates.some((item) => item.hash === state.selectedHash)) {
        state.selectedHash = candidates[0]?.hash || "";
      }
    } catch (error) {
      console.error(error);
      state.candidates = [];
      new Notice(`Write Responses failed: ${error.message}`, 10000);
    } finally {
      state.busy = false;
      render();
    }
  }

  function selected() {
    return state.candidates.find((item) => item.hash === state.selectedHash) || null;
  }

  async function writeResponses() {
    const item = selected();
    if (!item || item.blocked || state.busy) return;
    state.busy = true;
    state.result = null;
    render();
    try {
      const result = callFeeder(app, "writeback.commit", { commit: item.hash });
      state.result = result;
      const count = Array.isArray(result.written) ? result.written.length : 0;
      new Notice(`Wrote and committed ${count} response file(s).`);
      const candidates = callFeeder(app, "writeback.candidates", { limit: 200 });
      state.candidates = Array.isArray(candidates) ? candidates : [];
      state.selectedHash = state.candidates[0]?.hash || "";
    } catch (error) {
      console.error(error);
      new Notice(`Writeback failed: ${error.message}`, 10000);
    } finally {
      state.busy = false;
      render();
    }
  }

  function renderMembers(parent, item) {
    parent.appendChild(el("h2", {}, "Commit files"));
    const table = el("table", { style: "width:100%;" });
    const head = el("tr");
    for (const label of ["File", "Slug", "State"]) head.appendChild(el("th", {}, label));
    table.appendChild(head);

    for (const member of item.members || []) {
      const row = el("tr");
      const fileCell = el("td");
      const path = member.path || member.source_path;
      if (member.path) createInternalLink(fileCell, app, member.path, member.path);
      else fileCell.textContent = member.source_path;
      const stateText = member.error || member.git_status || member.state || "clean";
      row.append(fileCell, el("td", {}, member.slug || ""), el("td", {}, stateText));
      table.appendChild(row);
    }
    parent.appendChild(table);

    const blocked = (item.members || []).filter((member) => member.dirty || member.error);
    if (blocked.length) {
      const warning = el("div", { style: "margin-top:1rem;padding:.75rem;border:1px solid var(--background-modifier-error);" });
      warning.appendChild(el("strong", {}, "Writeback aborted."));
      warning.appendChild(el("p", {}, "One or more selected files are dirty or cannot be resolved. Open the linked files, resolve the problem, commit or discard the changes, then refresh."));
      parent.appendChild(warning);
    }
  }

  function renderResult(parent) {
    if (!state.result?.written?.length) return;
    parent.appendChild(el("h2", {}, "Written files"));
    const list = el("ul");
    for (const item of state.result.written) {
      const li = el("li");
      createInternalLink(li, app, item.path, `[[${item.path.replace(/\.md$/i, "")}]]`);
      list.appendChild(li);
    }
    parent.appendChild(list);
    parent.appendChild(el("p", {}, `Writeback commit: ${String(state.result.writeback_commit || "").slice(0, 8)}`));
  }

  function render() {
    container.replaceChildren();
    const toolbar = el("div", { style: "display:flex;gap:.75rem;align-items:center;flex-wrap:wrap;" });
    const refreshButton = el("button", { onclick: refresh }, "Refresh");
    refreshButton.disabled = state.busy;
    toolbar.appendChild(refreshButton);
    toolbar.appendChild(el("span", {}, state.busy ? "Loading…" : `${state.candidates.length} pending dispatch commit(s)`));
    container.appendChild(toolbar);

    if (!state.candidates.length) {
      container.appendChild(el("p", {}, state.busy ? "Loading inflight commits…" : "No inflight commits are awaiting writeback."));
      renderResult(container);
      return;
    }

    const label = el("label", { style: "display:block;margin-top:1rem;" }, "Dispatch commit");
    const select = el("select", { style: "display:block;width:100%;margin-top:.35rem;" });
    for (const item of state.candidates) {
      const text = `${item.short_hash} — ${item.subject} — ${item.plan_slug} — ${formatDate(item.tag_timestamp)}`;
      select.appendChild(el("option", { value: item.hash, selected: item.hash === state.selectedHash }, text));
    }
    select.onchange = () => { state.selectedHash = select.value; state.result = null; render(); };
    label.appendChild(select);
    container.appendChild(label);

    const item = selected();
    if (!item) return;
    container.appendChild(el("p", {}, `Plan: ${item.plan_slug} · Inflight tag: ${item.inflight_tag}`));
    renderMembers(container, item);

    const button = el("button", { onclick: writeResponses, style: "margin-top:1rem;" }, state.busy ? "Writing…" : "Write Responses");
    button.disabled = state.busy || item.blocked;
    container.appendChild(button);
    renderResult(container);
  }

  await refresh();
}

module.exports = { renderWriteResponses };
