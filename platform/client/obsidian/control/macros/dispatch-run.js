"use strict";

const path = require("node:path");
const { getFileManifest, appendClipboardCandidates } = require("../scripts/lib/file-manifest.js");
const { notify } = require("../scripts/lib/notify.js");
const { runDispatch, serviceCall } = require("../scripts/lib/dispatch-service.js");
const { loadConfig } = require("../scripts/lib/config-loader.js");

async function renderDispatchRun({ app, container }) {
  container.empty();
  const protocol = loadConfig("protocol");
  const session = getFileManifest(app);

  function planLabel(plan) {
    const slug = String(plan.record_identity || plan.slug || plan.key || "").trim();
    return String(plan.payload?.label || plan.label || plan.title || plan.name || slug);
  }

  function sortedPlans(plans) {
    return [...plans].sort((a, b) =>
      planLabel(a).localeCompare(planLabel(b), undefined, { sensitivity: "base", numeric: true }) ||
      String(a.record_identity || a.slug || a.key || "").localeCompare(
        String(b.record_identity || b.slug || b.key || ""),
        undefined,
        { sensitivity: "base", numeric: true }
      )
    );
  }

  const heading = container.createEl("h2", { text: "Dispatch candidate files" });
  heading.style.marginTop = "0";
  const toolbar = container.createEl("div");
  toolbar.style.cssText = "display:flex;gap:.5em;align-items:center;flex-wrap:wrap;margin-bottom:.75em";
  const refreshButton = toolbar.createEl("button", { text: "Refresh" });
  const freshness = toolbar.createEl("span", { text: "Loading service state…" });

  const selectionRow = container.createEl("div");
  selectionRow.style.cssText = "display:flex;gap:.5em;align-items:center;flex-wrap:wrap;margin-bottom:.75em";
  const status = selectionRow.createEl("div", { text: "Loading candidates…" });
  status.style.marginRight = "auto";
  const clearButton = selectionRow.createEl("button", { text: "Clear Dispatch List" });
  const selectAllButton = selectionRow.createEl("button", { text: "Select all" });
  const selectNoneButton = selectionRow.createEl("button", { text: "Select none" });
  const list = container.createEl("div");
  list.style.cssText = "display:grid;gap:.35em;margin-bottom:1em";

  function selectedDocumentSlugs() {
    const slugs = [];
    const seen = new Set();
    for (const item of session.candidates.values()) {
      if (!item.selected) continue;
      const file = app.vault.getAbstractFileByPath(item.path);
      if (!file || file.extension !== "md") throw new Error(`Selected Markdown file was not found: ${item.path}`);
      const slug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
      if (!slug) throw new Error(`Selected file is missing required slug property: ${item.path}`);
      if (seen.has(slug)) throw new Error(`Selected document slug is duplicated: ${slug}`);
      seen.add(slug); slugs.push(slug);
    }
    return slugs;
  }

  function renderCandidates(note = "") {
    list.empty();
    const candidates = [...session.candidates.values()];
    const selectedCount = candidates.filter((item) => item.selected).length;
    status.setText(candidates.length
      ? `${candidates.length} candidate${candidates.length === 1 ? "" : "s"}; ${selectedCount} selected${note ? ` — ${note}` : ""}`
      : `No candidate files in this vault session${note ? ` — ${note}` : ""}`);
    for (const item of candidates) {
      const row = list.createEl("label"); row.style.cssText = "display:flex;gap:.55em;align-items:baseline";
      const checkbox = row.createEl("input", { attr: { type: "checkbox" } }); checkbox.checked = item.selected;
      checkbox.addEventListener("change", () => { item.selected = checkbox.checked; renderCandidates(); });
      const text = row.createSpan(); text.createEl("strong", { text: item.title }); text.createSpan({ text: ` — ${item.path}` });
    }
  }

  async function addClipboardSelection() {
    try {
      const added = appendClipboardCandidates(app, session, await navigator.clipboard.readText());
      renderCandidates(added ? `added ${added} from clipboard` : "clipboard contained no new file references");
    } catch (error) { renderCandidates(`could not read clipboard: ${error.message || error}`); }
  }

  clearButton.addEventListener("click", () => { session.candidates.clear(); renderCandidates("dispatch list cleared"); notify("Dispatch list cleared."); });
  selectAllButton.addEventListener("click", () => { for (const item of session.candidates.values()) item.selected = true; renderCandidates(); });
  selectNoneButton.addEventListener("click", () => { for (const item of session.candidates.values()) item.selected = false; renderCandidates(); });
  await addClipboardSelection();

  const snapshotSpec = protocol.service_operations?.define_plan_snapshot || {};
  const snapshotResult = await serviceCall(app, String(snapshotSpec.command || "define-plan-snapshot"), { version: Number(snapshotSpec.request_version || 1) });
  const snapshot = JSON.parse(String(snapshotResult.stdout || "{}").trim() || "{}");
  if (!snapshot.ok) throw new Error(snapshot.error || "Could not load service state");
  freshness.setText(snapshot.refreshed_at ? `Service state: ${snapshot.refreshed_at}` : "Service state has not been refreshed yet.");
  const planRows = Array.isArray(snapshot.catalogs?.plans) ? snapshot.catalogs.plans : [];

  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    try {
      const spec = protocol.service_operations?.dispatch_refresh || {};
      const response = await serviceCall(app, String(spec.command || "dispatch-refresh"), {
        version: Number(spec.request_version || 1),
      });
      const output = JSON.parse(String(response.stdout || "{}").trim() || "{}");
      if (!output.ok) throw new Error(output.error || "Dispatch refresh failed");
      notify(`Refresh complete: ${output.uploaded_instructions || 0} instruction(s) uploaded.`);
      await renderDispatchRun({ app, container });
    } catch (error) { notify(`Refresh failed: ${error.message || error}`, 10000); }
    finally { refreshButton.disabled = false; }
  });

  if (!planRows.length) {
    container.createEl("p", { text: "No plans are available in service state. Use Refresh if you expect one." });
    return;
  }

  const form = container.createEl("div"); form.style.cssText = "display:grid;gap:.6em;max-width:42em";
  form.createEl("label", { text: "Plan" });
  const select = form.createEl("select");
  for (const plan of sortedPlans(planRows)) {
    const slug = String(plan.record_identity || plan.slug || plan.key || "").trim();
    if (!slug) continue;
    select.createEl("option", { text: planLabel(plan), value: slug });
  }

  const combineRow = form.createEl("label"); combineRow.style.cssText = "display:flex;gap:.5em;align-items:center";
  const combine = combineRow.createEl("input", { attr: { type: "checkbox" } }); combineRow.createSpan({ text: "Combine selected files" });
  form.createEl("label", { text: "Combined record basename" });
  const combineBasename = form.createEl("input", { attr: { type: "text", placeholder: "Example: chapter-one", disabled: "disabled" } });
  combine.addEventListener("change", () => { combineBasename.disabled = !combine.checked; if (combine.checked) combineBasename.focus(); });

  const runButton = form.createEl("button", { text: "Dispatch Run", cls: "mod-cta" });
  const result = container.createEl("pre"); result.style.whiteSpace = "pre-wrap";
  runButton.addEventListener("click", async () => {
    runButton.disabled = true; result.setText("Sending document and plan slugs to service…");
    try {
      const documents = selectedDocumentSlugs();
      if (!documents.length) throw new Error("Select at least one candidate file.");
      if (combine.checked && !combineBasename.value.trim()) throw new Error("Enter a basename for the combined record.");
      if (combine.checked) throw new Error("Combined dispatch is not yet available through service.");
      const transport = await runDispatch(app, { documents, plan: select.value });
      for (const [key, item] of session.candidates.entries()) {
        if (item.selected) session.candidates.delete(key);
      }
      renderCandidates("dispatched files removed");
      result.setText(`Dispatch uploaded and enqueued by service.\nPlan: ${transport.plan}\nRecords: ${transport.records}`);
    } catch (error) {
      const detail = String(error?.message || error || "Unknown dispatch error");
      result.setText(`Dispatch failed.\n${detail}`); notify(`Dispatch failed: ${detail}`, 10000);
    } finally { runButton.disabled = false; }
  });
}

module.exports = async function dispatch_run(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const { openWorkflowModal } = require(path.join(root, "_control/scripts/lib/workflow-modal.js"));
  return openWorkflowModal({ app, title: "Dispatch Run", render: (container) => renderDispatchRun({ app, container }) });
};
