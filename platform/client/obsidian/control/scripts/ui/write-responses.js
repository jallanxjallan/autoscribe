"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const path = nodeRequire("node:path");

async function renderWriteResponses({ app, container }) {
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relative) => nodeRequire(path.join(root, "_control", ...relative.split("/")));
  const { notify } = load("scripts/lib/notify.js");
  const transport = load("scripts/lib/dispatch-service.js");
  const { loadConfig } = load("scripts/lib/config-loader.js");
  const ui = () => loadConfig("ui");
  const workflow = () => loadConfig("workflow");
  const protocol = () => loadConfig("protocol");
  const state = { busy: false, rows: [], error: "", message: "" };

  function parseNdjson(text) {
    return String(text || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
      .map((line, index) => {
        try { return JSON.parse(line); }
        catch (error) { throw new Error(`Invalid writeback manifest on line ${index + 1}: ${error.message}`); }
      });
  }

  function short(value) {
    const text = String(value || "");
    return text ? text.slice(0, 8) : String(ui().missing_value || "—");
  }

  function render() {
    container.replaceChildren();
    container.createEl("h2", { text: "Write Responses" });
    container.createEl("p", {
      text: `Rust checkpoints dirty targets, overwrites pending responses, marks them ${workflow().writeback?.status} / ${workflow().writeback?.producer}, and commits each writeback.`,
    });
    const toolbar = container.createEl("div");
    toolbar.style.cssText = "display:flex;gap:.6rem;align-items:center;margin:.6rem 0 1rem";
    const runButton = toolbar.createEl("button", { text: state.busy ? "Writing…" : "Write Responses", cls: "mod-cta" });
    runButton.disabled = state.busy;
    runButton.onclick = runWritebacks;
    toolbar.createSpan({ text: state.message });
    if (state.error) {
      const error = container.createEl("pre", { text: state.error });
      error.style.whiteSpace = "pre-wrap";
    }
    if (!state.rows.length) return;
    const table = container.createEl("table");
    table.style.width = "100%";
    const head = table.createEl("tr");
    for (const label of (ui().write_response_columns || [])) {
      head.createEl("th", { text: label });
    }
    for (const row of state.rows) {
      const tr = table.createEl("tr");
      tr.createEl("td", { text: row.source_identity || String(ui().missing_value || "—") });
      const pathCell = tr.createEl("td");
      if (row.path) {
        const link = pathCell.createEl("a", { text: row.path, href: "#" });
        link.onclick = (event) => { event.preventDefault(); app.workspace.openLinkText(row.path, "", false); };
      } else pathCell.setText(String(ui().missing_value || "—"));
      const outcome = row.status === protocol().writeback?.success_status ? "Committed" : `Failed: ${row.error || "unknown error"}`;
      tr.createEl("td", { text: outcome });
      tr.createEl("td", { text: short(row.checkpoint_commit) });
      tr.createEl("td", { text: short(row.commit) });
      tr.createEl("td", { text: row.status === protocol().writeback?.success_status ? `status: ${workflow().writeback?.status} · producer: ${workflow().writeback?.producer}` : String(ui().missing_value || "—") });
    }
  }

  async function runWritebacks() {
    if (state.busy) return;
    state.busy = true;
    state.error = "";
    state.message = "Retrieving and writing pending responses…";
    render();
    notify("Writing pending responses…");
    try {
      const response = await transport.serviceCall(app, String(protocol().writeback?.command), { version: Number(protocol().writeback?.request_version || 1) });
      state.rows = parseNdjson(response.stdout).filter((row) => row.type === protocol().writeback?.result_type);
      const committed = state.rows.filter((row) => row.status === protocol().writeback?.success_status).length;
      const failed = state.rows.length - committed;
      state.message = state.rows.length
        ? `${committed} committed${failed ? `; ${failed} failed` : ""}.`
        : "No pending responses.";
      notify(`Write Responses complete: ${state.message}`, failed ? 10000 : 6000);
    } catch (error) {
      state.rows = [];
      state.error = error.message || String(error);
      state.message = "Write Responses failed.";
      notify(`${state.message} ${state.error}`, 10000);
    } finally {
      state.busy = false;
      render();
    }
  }

  render();
  await runWritebacks();
}

module.exports = { renderWriteResponses };
