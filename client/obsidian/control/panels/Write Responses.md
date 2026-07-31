# Write Responses

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const { listTransportRuns, applyResponseBranch } = loadControl("scripts/lib/git-transport.js");
const { createInternalLink } = loadControl("scripts/lib/internal-link.js");

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

function short(value, width = 8) {
  return String(value || "").slice(0, width);
}

function wikilinkLabel(path) {
  return `[[${String(path || "").replace(/\.md$/i, "")}]]`;
}

function formatRun(run) {
  const when = run.created_at ? new Date(run.created_at).toLocaleString() : "unknown time";
  return `${run.plan_identity || "unknown plan"} · ${run.count} file${run.count === 1 ? "" : "s"} · ${when}`;
}

function renderRecords(parent, app, title, records, note = "") {
  if (!Array.isArray(records) || !records.length) return;
  parent.appendChild(el("h2", {}, title));
  if (note) parent.appendChild(el("p", {}, note));
  const list = el("ul");
  for (const record of records) {
    const li = el("li");
    if (record.path) createInternalLink(li, app, record.path, wikilinkLabel(record.path));
    else li.textContent = record.identity || record.source_path || "unknown record";
    if (record.identity) li.appendChild(document.createTextNode(` — ${record.identity}`));
    list.appendChild(li);
  }
  parent.appendChild(list);
}

async function renderWriteResponses({ app, container }) {
  const state = {
    busy: false,
    runs: [],
    selectedBranch: "",
    result: null,
    error: "",
  };

  function loadRuns() {
    state.runs = listTransportRuns(app);
    const ready = state.runs.filter((run) => run.status === "response_ready");
    if (!ready.some((run) => run.branch === state.selectedBranch)) {
      state.selectedBranch = ready[0]?.branch || "";
    }
  }

  async function refresh() {
    state.error = "";
    state.result = null;
    try {
      loadRuns();
    } catch (error) {
      state.error = error.message || String(error);
    }
    render();
  }

  async function writeSelected() {
    if (state.busy || !state.selectedBranch) return;
    state.busy = true;
    state.result = null;
    state.error = "";
    render();
    try {
      state.result = applyResponseBranch(app, state.selectedBranch);
      if (state.result.conflicts?.length) {
        new Notice(`Response applied with ${state.result.conflicts.length} merge conflict(s).`, 10000);
      } else {
        new Notice(`Wrote ${state.result.written.length} response file(s).`);
      }
      loadRuns();
    } catch (error) {
      console.error(error);
      state.error = error.message || String(error);
      new Notice(`Writeback failed: ${state.error}`, 10000);
    } finally {
      state.busy = false;
      render();
    }
  }

  function renderRunSummary(parent, run) {
    if (!run) return;
    const details = el("div", { style: "margin: 0.75em 0;" });
    details.appendChild(el("div", {}, `Branch: ${run.branch}`));
    details.appendChild(el("div", {}, `Run: ${run.run_identity}`));
    details.appendChild(el("div", {}, `Plan: ${run.plan_identity || "—"}`));
    details.appendChild(el("div", {}, `Source: ${run.source_branch || "—"} @ ${short(run.source_commit) || "—"}`));
    parent.appendChild(details);

    renderRecords(parent, app, "Returned files", run.response?.records || run.dispatch?.records || []);
  }

  function renderResult(parent) {
    if (!state.result) return;
    renderRecords(parent, app, "Written files", state.result.written);
    renderRecords(
      parent,
      app,
      "Merge conflicts",
      state.result.conflicts,
      "The response bodies were written with Git conflict markers. Resolve them manually, then commit on the editorial branch. The transport branch remains unacknowledged.",
    );
    if (state.result.committed) {
      parent.appendChild(el(
        "p",
        {},
        `Committed writeback ${short(state.result.target_commit)} on ${state.result.target_branch}.`,
      ));
    }
  }

  function render() {
    container.replaceChildren();
    container.appendChild(el(
      "p",
      {},
      "Apply a completed transport-branch response to the current editorial branch. Current frontmatter is preserved and bodies are merged against the dispatched version.",
    ));

    const toolbar = el("div", { style: "display:flex; gap:0.5em; align-items:center; flex-wrap:wrap;" });
    const refreshButton = el("button", { onclick: refresh, disabled: state.busy }, "Refresh");
    toolbar.appendChild(refreshButton);

    const readyRuns = state.runs.filter((run) => run.status === "response_ready");
    const select = el("select", { disabled: state.busy || !readyRuns.length });
    for (const run of readyRuns) {
      const option = el("option", { value: run.branch }, formatRun(run));
      if (run.branch === state.selectedBranch) option.selected = true;
      select.appendChild(option);
    }
    select.addEventListener("change", () => {
      state.selectedBranch = select.value;
      state.result = null;
      render();
    });
    toolbar.appendChild(select);

    const writeButton = el(
      "button",
      { onclick: writeSelected, disabled: state.busy || !state.selectedBranch },
      state.busy ? "Writing Response…" : "Write Response",
    );
    toolbar.appendChild(writeButton);
    container.appendChild(toolbar);

    if (state.error) container.appendChild(el("pre", { style: "white-space:pre-wrap;" }, state.error));
    if (!readyRuns.length && !state.error) {
      container.appendChild(el("p", {}, "No completed transport branches are waiting for writeback."));
    }

    const selected = readyRuns.find((run) => run.branch === state.selectedBranch);
    renderRunSummary(container, selected);
    renderResult(container);

    const waiting = state.runs.filter((run) => run.status === "waiting");
    const completed = state.runs.filter((run) => run.status === "written_back");
    if (waiting.length || completed.length) {
      const status = el("details", { style: "margin-top:1em;" });
      status.appendChild(el("summary", {}, `Other runs: ${waiting.length} waiting, ${completed.length} written back`));
      if (waiting.length) {
        status.appendChild(el("h3", {}, "Waiting for feeder"));
        const list = el("ul");
        for (const run of waiting) list.appendChild(el("li", {}, `${formatRun(run)} — ${run.branch}`));
        status.appendChild(list);
      }
      if (completed.length) {
        status.appendChild(el("h3", {}, "Written back"));
        const list = el("ul");
        for (const run of completed) list.appendChild(el("li", {}, `${formatRun(run)} — ${run.branch}`));
        status.appendChild(list);
      }
      container.appendChild(status);
    }
  }

  await refresh();
}

await renderWriteResponses({ app, container: dv.container });
````
