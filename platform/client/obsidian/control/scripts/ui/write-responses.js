"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const runtimeApp = globalThis.app;
const controlVaultRoot = runtimeApp.vault.adapter.getBasePath?.() || runtimeApp.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const { listTransportRuns, getResponseReview, decideResponse } = loadControl("scripts/lib/git-transport.js");
const { element: el, renderDiff } = loadControl("scripts/lib/diff-view.js");
const { runFeederCommand } = loadControl("scripts/lib/feeder-command.js");
const { notify } = loadControl("scripts/lib/notify.js");

function formatRun(run) {
  const when = run.created_at ? new Date(run.created_at).toLocaleString() : "unknown time";
  return `${run.plan_identity || "unknown plan"} · ${run.pending?.length || 0} pending · ${when}`;
}

async function renderWriteResponses({ app, container }) {
  const state = { busy: false, retrieving: true, runs: [], branch: "", identity: "", review: null, error: "", notice: "Retrieving available results…" };

  function loadRuns() {
    state.runs = listTransportRuns(app).filter((run) => run.status === "response_pending");
    if (!state.runs.some((run) => run.branch === state.branch)) state.branch = state.runs[0]?.branch || "";
    const selectedRun = state.runs.find((run) => run.branch === state.branch);
    if (!selectedRun?.pending?.some((record) => record.identity === state.identity)) state.identity = selectedRun?.pending?.[0]?.identity || "";
    state.review = state.branch && state.identity ? getResponseReview(app, state.branch, state.identity) : null;
  }

  function refresh(notifyUser = true) {
    if (notifyUser) notify("Refreshing response review…");
    state.error = "";
    try { loadRuns(); } catch (error) { state.error = error.message || String(error); state.review = null; }
    render();
    if (notifyUser) notify(state.error ? `Response refresh failed: ${state.error}` : "Response review refreshed.", state.error ? 10000 : 4000);
  }

  function decideOne(outcome) {
    if (state.busy || !state.branch || !state.identity) return;
    notify(`${outcome === "accepted" ? "Accepting" : "Declining"} response ${state.identity}…`);
    state.busy = true; state.error = ""; state.notice = ""; render();
    try {
      const result = decideResponse(app, state.branch, state.identity, outcome);
      state.notice = `${result.identity} ${outcome}.`;
      notify(state.notice);
      loadRuns();
    } catch (error) {
      console.error(error); state.error = error.message || String(error);
      notify(`Response decision failed: ${state.error}`, 10000);
    } finally { state.busy = false; render(); }
  }

  function decideAll(outcome) {
    if (state.busy || !state.branch) return;
    const run = state.runs.find((item) => item.branch === state.branch);
    const records = [...(run?.pending || [])];
    if (!records.length) return;
    const verb = outcome === "accepted" ? "accept" : "decline";
    if (!window.confirm(`Are you sure you want to ${verb} all ${records.length} responses in the selected run?`)) return;
    notify(`${outcome === "accepted" ? "Accepting" : "Declining"} ${records.length} response(s)…`);
    state.busy = true; state.error = ""; state.notice = ""; render();
    let completed = 0;
    try {
      for (const record of records) {
        decideResponse(app, state.branch, record.identity, outcome);
        completed += 1;
      }
      state.notice = `${completed} response${completed === 1 ? "" : "s"} ${outcome}.`;
      notify(state.notice);
      loadRuns();
    } catch (error) {
      console.error(error);
      state.error = `${completed} completed before failure: ${error.message || error}`;
      notify(`Bulk response decision stopped: ${state.error}`, 10000);
      loadRuns();
    } finally { state.busy = false; render(); }
  }

  function render() {
    container.replaceChildren();
    container.appendChild(el("p", {}, "Accept writes the response, records the pipeline run, and sets action: review. Decline leaves the source unchanged. Each decision is committed and can later be reconsidered from File State."));

    const bulk = el("div", { style: "display:flex;gap:0.5em;align-items:center;flex-wrap:wrap;padding:0.65em;border:1px solid var(--background-modifier-border);border-radius:6px;margin-bottom:0.8em;" });
    const acceptAll = el("button", { onclick: () => decideAll("accepted"), disabled: state.busy || !state.branch }, "Accept All");
    const declineAll = el("button", { onclick: () => decideAll("declined"), disabled: state.busy || !state.branch }, "Decline All");
    bulk.append(el("strong", {}, "Whole selected run:"), acceptAll, declineAll);
    container.appendChild(bulk);

    const toolbar = el("div", { style: "display:flex;gap:0.5em;align-items:center;flex-wrap:wrap;margin-bottom:0.8em;" });
    toolbar.appendChild(el("button", { onclick: refresh, disabled: state.busy }, "Refresh"));
    const branchSelect = el("select", { disabled: state.busy || !state.runs.length });
    for (const run of state.runs) {
      const option = el("option", { value: run.branch }, formatRun(run));
      if (run.branch === state.branch) option.selected = true;
      branchSelect.appendChild(option);
    }
    branchSelect.addEventListener("change", () => { state.branch = branchSelect.value; state.identity = ""; refresh(false); });
    toolbar.appendChild(branchSelect);
    const run = state.runs.find((item) => item.branch === state.branch);
    const recordSelect = el("select", { disabled: state.busy || !run?.pending?.length });
    for (const record of run?.pending || []) {
      const option = el("option", { value: record.identity }, `${record.identity} — ${record.source_path || "unknown path"}`);
      if (record.identity === state.identity) option.selected = true;
      recordSelect.appendChild(option);
    }
    recordSelect.addEventListener("change", () => { state.identity = recordSelect.value; refresh(false); });
    toolbar.appendChild(recordSelect); container.appendChild(toolbar);

    if (state.error) container.appendChild(el("pre", { style: "white-space:pre-wrap;" }, state.error));
    if (state.notice) container.appendChild(el("p", {}, state.notice));
    if (state.retrieving) { container.appendChild(el("p", {}, "Retrieving available results from feeder…")); return; }
    if (!state.runs.length && !state.error) { container.appendChild(el("p", {}, "No downloaded responses await a decision.")); return; }
    if (!state.review) return;
    container.appendChild(el("div", { style: "margin-bottom:0.75em;" }, `Branch: ${state.branch}`));
    renderDiff(container, state.review);
    const actions = el("div", { style: "display:flex;gap:0.75em;margin-top:1em;" });
    actions.appendChild(el("button", { onclick: () => decideOne("accepted"), disabled: state.busy }, state.busy ? "Working…" : "Accept overwrite"));
    actions.appendChild(el("button", { onclick: () => decideOne("declined"), disabled: state.busy }, "Decline overwrite"));
    container.appendChild(actions);
  }
  render();
  try {
    const retrieval = await runFeederCommand(app, ["retrieve-results"]);
    const lines = [retrieval.stdout, retrieval.stderr]
      .flatMap((value) => String(value || "").split(/\r?\n/))
      .map((line) => line.trim())
      .filter(Boolean);
    state.notice = lines.find((line) => line.startsWith("retrieve-results:")) || "Result retrieval completed.";
  } catch (error) {
    const message = error.message || String(error);
    if (/no waiting autoscribe\/run\/\* branch found|no waiting|no claimed/i.test(message)) {
      state.notice = "No claimed runs currently have results to retrieve.";
    } else {
      console.error(error);
      state.error = message;
      state.notice = "Result retrieval failed. Use obs log from this vault for details.";
    }
  } finally {
    state.retrieving = false;
    try { loadRuns(); }
    catch (error) { state.error = state.error || error.message || String(error); state.review = null; }
    render();
  }
}


module.exports = { renderWriteResponses };
