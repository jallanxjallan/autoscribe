"use strict";

module.exports = async function write_responses(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relativePath) => nodeRequire(path.join(base, "_control", ...relativePath.split("/")));

  const { openWorkflowModal } = load("scripts/lib/workflow-modal.js");
  const { notify } = load("scripts/lib/notify.js");
  const { readSystemState } = load("scripts/lib/system-state.js");
  const { serviceCall } = load("scripts/lib/dispatch-service.js");
  const { loadConfig } = load("scripts/lib/config-loader.js");

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

  async function render(container) {
    container.empty();

    const heading = container.createEl("h2", { text: "Write Responses" });
    heading.style.marginTop = "0";

    const toolbar = container.createEl("div");
    toolbar.style.cssText = "display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.6rem 0 1rem";
    const refreshButton = toolbar.createEl("button", { text: "Refresh" });
    refreshButton.type = "button";
    const refreshStatus = toolbar.createSpan({ text: "" });

    container.createEl("p", {
      text: "Writes completed pipeline responses into their source files. Existing frontmatter is preserved; the files remain dirty for vault-specific post-processing.",
    });

    const summary = container.createEl("div", { text: "Loading pending responses…" });
    summary.style.marginBottom = ".75rem";

    const results = container.createEl("div");
    results.style.marginTop = "1rem";

    async function refreshState() {
      refreshStatus.setText("Reading current service state…");
      try {
        const system = await readSystemState(app);
        if (!system.pipeline) {
          throw new Error(system.errors?.pipeline || "Pipeline state unavailable");
        }
        const pending = Number(system.pipeline.counts?.response_pending || 0);
        summary.setText(
          pending
            ? `${pending} pending response${pending === 1 ? "" : "s"} ready to write.`
            : "No pending responses."
        );
        refreshStatus.setText(`Updated ${new Date(system.refreshed_at).toLocaleTimeString()}`);
      } catch (error) {
        const message = error?.message || String(error);
        summary.setText("Pending-response state unavailable.");
        refreshStatus.setText(`Refresh failed: ${message}`);
      }
    }

    refreshButton.addEventListener("click", async () => {
      if (refreshButton.disabled) return;
      refreshButton.disabled = true;
      refreshButton.setText("Refreshing…");
      refreshStatus.setText("Checking for completed responses…");
      results.empty();

      try {
        const spec = protocol().writeback || {};
        const response = await serviceCall(
          app,
          String(spec.command || "write-responses"),
          { version: Number(spec.request_version || 1) }
        );

        const rows = parseNdjson(response.stdout)
          .filter((row) => row.type === String(spec.result_type || "writeback-result"));

        const successStatus = String(spec.success_status || "written");
        const written = rows.filter((row) => row.status === successStatus);
        const failed = rows.filter((row) => row.status !== successStatus);

        if (!rows.length) {
          results.createEl("p", { text: "No pending responses." });
        } else {
          const table = results.createEl("table");
          table.style.width = "100%";

          const head = table.createEl("tr");
          for (const label of ["Source", "Path", "Outcome"]) {
            head.createEl("th", { text: label });
          }

          for (const row of rows) {
            const tr = table.createEl("tr");
            tr.createEl("td", { text: String(row.source_identity || "—") });

            const pathCell = tr.createEl("td");
            if (row.path) {
              const link = pathCell.createEl("a", { text: String(row.path), href: "#" });
              link.addEventListener("click", (event) => {
                event.preventDefault();
                app.workspace.openLinkText(String(row.path), "", false);
              });
            } else {
              pathCell.setText("—");
            }

            tr.createEl("td", {
              text: row.status === successStatus
                ? "Written"
                : `Failed: ${row.error || "unknown error"}`,
            });
          }
        }

        const message = `${written.length} written${failed.length ? `; ${failed.length} failed` : ""}.`;
        notify(`Write Responses complete: ${message}`, failed.length ? 10000 : 6000);
        await refreshState();
      } catch (error) {
        const message = error?.message || String(error);
        results.createEl("pre", { text: `Write Responses failed.\n${message}` }).style.whiteSpace = "pre-wrap";
        refreshStatus.setText(`Refresh failed: ${message}`);
        notify(`Write Responses failed: ${message}`, 10000);
      } finally {
        refreshButton.disabled = false;
        refreshButton.setText("Refresh");
      }
    });

    await refreshState();
  }

  return openWorkflowModal({
    app,
    title: "Write Responses",
    render: (container) => render(container),
  });
};
