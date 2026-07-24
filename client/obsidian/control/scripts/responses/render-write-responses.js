"use strict";

const { callFeeder } = require("../lib/feeder-ipc");
const { createInternalLink } = require("../lib/internal-link");

function el(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  if (text !== null) node.textContent = text;
  return node;
}

function wikilinkLabel(path) {
  return `[[${String(path || "").replace(/\.md$/i, "")}]]`;
}

function renderFileList(parent, app, title, items, note = "") {
  if (!Array.isArray(items) || !items.length) return;
  parent.appendChild(el("h2", {}, title));
  if (note) parent.appendChild(el("p", {}, note));
  const list = el("ul");
  for (const item of items) {
    const li = el("li");
    const path = item.path || item.source_path;
    if (item.path) createInternalLink(li, app, item.path, wikilinkLabel(item.path));
    else li.textContent = wikilinkLabel(path);
    if (item.short_source_commit) {
      li.appendChild(document.createTextNode(` — source ${item.short_source_commit}`));
    }
    if (item.error) {
      li.appendChild(document.createTextNode(` — ${item.error}`));
    }
    list.appendChild(li);
  }
  parent.appendChild(list);
}

async function renderWriteResponses({ app, container }) {
  const state = { busy: false, result: null };

  async function runWriteback() {
    if (state.busy) return;
    state.busy = true;
    state.result = null;
    render();
    try {
      state.result = callFeeder(app, "writeback.run", {});
      const written = Array.isArray(state.result?.written) ? state.result.written.length : 0;
      const waiting = Array.isArray(state.result?.not_available) ? state.result.not_available.length : 0;
      new Notice(`Wrote ${written} response file(s); ${waiting} inflight file(s) still waiting.`);
    } catch (error) {
      console.error(error);
      new Notice(`Writeback failed: ${error.message}`, 10000);
    } finally {
      state.busy = false;
      render();
    }
  }

  function renderResult(parent) {
    const result = state.result;
    if (!result) return;

    renderFileList(parent, app, "Downloaded files", result.written);
    renderFileList(
      parent,
      app,
      "Edited while inflight",
      result.modified_while_inflight,
      "These files were committed and tagged before the AI response overwrote them. Their state is set to ‘edited while inflight’; inspect the Git diff carefully.",
    );
    renderFileList(
      parent,
      app,
      "Not yet available from AutoScribe",
      result.not_available,
      "These files remain inflight, but asc has not yet exposed a response for download.",
    );
    renderFileList(
      parent,
      app,
      "Unresolved inflight files",
      result.unresolved,
      "These inflight source files could not be resolved safely to a current vault file.",
    );

    if (result.preservation_commit) {
      const tag = result.preservation_tag ? ` · tag ${result.preservation_tag}` : "";
      parent.appendChild(el(
        "p",
        {},
        `Preserved inflight edits in commit ${String(result.preservation_commit).slice(0, 8)}${tag}.`,
      ));
    }

    if (!(result.written || []).length && !(result.not_available || []).length && !(result.unresolved || []).length) {
      parent.appendChild(el("p", {}, "No unfinished inflight files were found."));
    }
  }

  function render() {
    container.replaceChildren();
    container.appendChild(el(
      "p",
      {},
      "Write every response currently available for all inflight files in this repository.",
    ));
    const button = el(
      "button",
      { onclick: runWriteback, disabled: state.busy },
      state.busy ? "Writing Responses…" : "Write Responses",
    );
    container.appendChild(button);
    renderResult(container);
  }

  render();
}

module.exports = { renderWriteResponses };
