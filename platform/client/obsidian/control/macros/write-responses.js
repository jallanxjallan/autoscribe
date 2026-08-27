"use strict";

function createControlRuntime(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const loaderPath = path.join(base, "_control", "scripts", "lib", "control-loader.js");
  try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
  const { createControlLoader } = nodeRequire(loaderPath);
  return createControlLoader({ app, controlRoot: "_control" });
}

module.exports = async function write_responses(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const loader = createControlRuntime(app);
  const { openWorkflowModal } = loader.requireControl("scripts/lib/workflow-modal.js");
  const { notify } = loader.requireControl("scripts/lib/notify.js");
  const { serviceCall } = loader.requireControl("scripts/lib/service-command.js");
  const { loadConfig } = loader.requireControl("scripts/lib/config-loader.js");

  const protocol = () => loadConfig("protocol");

  function parseNdjson(text) {
    return String(text || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        try {
          return JSON.parse(line);
        } catch (error) {
          throw new Error(`Invalid writeback manifest on line ${index + 1}: ${error.message}`);
        }
      });
  }

  function pathCell(tr, row) {
    const cell = tr.createEl("td");
    if (!row.path) {
      cell.setText("—");
      return;
    }
    const link = cell.createEl("a", { text: String(row.path), href: "#" });
    link.addEventListener("click", (event) => {
      event.preventDefault();
      app.workspace.openLinkText(String(row.path), "", false);
    });
  }

  function reasonText(row) {
    if (row.status === "ready") return "Ready to write";
    if (row.status === "written") return "Written; review copy left dirty";
    if (row.status === "written-pending-ack") return "Written; export acknowledgement pending";
    if (row.status === "failed") return `Failed: ${row.error || "unknown error"}`;
    if (row.reason === "master-dirty") return "Decision required: master already dirty";
    if (row.reason === "changed-since-dispatch") return "Decision required: changed since dispatch";
    return "Decision required";
  }

  function addTable(parent, title, rows) {
    if (!rows.length) return;
    parent.createEl("h3", { text: title });
    const table = parent.createEl("table");
    table.style.width = "100%";
    const head = table.createEl("tr");
    for (const label of ["Source", "Path", "Master", "Dispatch source", "State"]) {
      head.createEl("th", { text: label });
    }
    for (const row of rows) {
      const tr = table.createEl("tr");
      tr.createEl("td", { text: String(row.source_identity || "—") });
      pathCell(tr, row);
      tr.createEl("td", { text: String(row.master_state || row.master_state_after || row.master_state_before || "—") });
      tr.createEl("td", {
        text: row.source_state === "matches-dispatch"
          ? "unchanged"
          : row.source_state === "changed-since-dispatch"
            ? "changed"
            : String(row.source_state || "—"),
      });
      tr.createEl("td", { text: reasonText(row) });
    }
  }

  async function render(container) {
    container.empty();

    const heading = container.createEl("h2", { text: "Write Responses" });
    heading.style.marginTop = "0";

    container.createEl("p", {
      text: "AutoScribe never commits the editorial branch. Clean, unchanged targets can be written automatically and are then left dirty for review. Dirty targets, or clean targets changed since dispatch, require a human decision.",
    });

    const toolbar = container.createEl("div");
    toolbar.style.cssText = "display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.6rem 0 1rem";
    const refreshButton = toolbar.createEl("button", { text: "Refresh state" });
    refreshButton.type = "button";
    const writeButton = toolbar.createEl("button", { text: "Write clean responses" });
    writeButton.type = "button";
    const status = toolbar.createSpan({ text: "" });

    const summary = container.createEl("div", { text: "Loading response state…" });
    summary.style.marginBottom = ".75rem";
    const results = container.createEl("div");

    function setBusy(busy) {
      refreshButton.disabled = busy;
      writeButton.disabled = busy;
    }

    async function load(apply) {
      setBusy(true);
      status.setText(apply ? "Writing safe targets…" : "Reading target state…");
      try {
        const spec = protocol().writeback || {};
        const response = await serviceCall(
          app,
          String(spec.command || "write-responses"),
          { version: Number(spec.request_version || 1), apply: Boolean(apply) }
        );
        const rows = parseNdjson(response.stdout)
          .filter((row) => row.type === String(spec.result_type || "writeback-result"));

        const ready = rows.filter((row) => row.status === "ready");
        const decisions = rows.filter((row) => row.status === "decision-required");
        const written = rows.filter((row) => row.status === "written" || row.status === "written-pending-ack");
        const failed = rows.filter((row) => row.status === "failed");

        summary.setText(rows.length
          ? `${ready.length} clean and ready; ${decisions.length} require a decision; ${written.length} written; ${failed.length} failed.`
          : "No pending responses.");

        results.empty();
        if (!rows.length) {
          results.createEl("p", { text: "No pending responses." });
        } else {
          addTable(results, "Clean on master", ready);
          addTable(results, "Decision required", decisions);
          addTable(results, "Written for review", written);
          addTable(results, "Failures", failed);
        }

        status.setText(`Updated ${new Date().toLocaleTimeString()}`);
        if (apply) {
          notify(
            `Write Responses: ${written.filter((row) => row.status === "written").length} written; ${decisions.length} require a decision${failed.length ? `; ${failed.length} failed` : ""}.`,
            failed.length ? 10000 : 6000
          );
        }
      } catch (error) {
        const message = error?.message || String(error);
        results.empty();
        results.createEl("pre", { text: `Write Responses failed.\n${message}` }).style.whiteSpace = "pre-wrap";
        summary.setText("Response state unavailable.");
        status.setText(`Failed: ${message}`);
        notify(`Write Responses failed: ${message}`, 10000);
      } finally {
        setBusy(false);
      }
    }

    refreshButton.addEventListener("click", () => load(false));
    writeButton.addEventListener("click", () => load(true));

    await load(false);
  }

  return openWorkflowModal({
    app,
    title: "Write Responses",
    render: (container) => render(container),
  });
};
