"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");

async function renderDispatchRun({ app, container }) {
  container.empty();
  const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const loadControl = (relativePath) => nodeRequire(pathMod.join(vaultRoot, "_control", ...relativePath.split("/")));
  const { getFileManifest, appendClipboardCandidates } = loadControl("scripts/lib/file-manifest.js");
  const { notify } = loadControl("scripts/lib/notify.js");
  const { runDispatch, serviceCall } = loadControl("scripts/lib/dispatch-service.js");

  const session = getFileManifest(app);
  const heading = container.createEl("h2", { text: "Dispatch candidate files" });
  heading.style.marginTop = "0";

  const selectionRow = container.createEl("div");
  selectionRow.style.display = "flex";
  selectionRow.style.gap = "0.5em";
  selectionRow.style.alignItems = "center";
  selectionRow.style.flexWrap = "wrap";
  selectionRow.style.marginBottom = "0.75em";

  const status = selectionRow.createEl("div", { text: "Loading candidates…" });
  status.style.marginRight = "auto";
  const clearButton = selectionRow.createEl("button", { text: "Clear Dispatch List" });
  const selectAllButton = selectionRow.createEl("button", { text: "Select all" });
  const selectNoneButton = selectionRow.createEl("button", { text: "Select none" });
  const list = container.createEl("div");
  list.style.display = "grid";
  list.style.gap = "0.35em";
  list.style.marginBottom = "1em";

  function selectedPaths() {
    return [...session.candidates.values()].filter((item) => item.selected).map((item) => item.path);
  }

  function selectedDocumentSlugs() {
    const slugs = [];
    const seen = new Set();
    for (const selectedPath of selectedPaths()) {
      const file = app.vault.getAbstractFileByPath(selectedPath);
      if (!file || file.extension !== "md") throw new Error(`Selected Markdown file was not found: ${selectedPath}`);
      const slug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
      if (!slug) throw new Error(`Selected file is missing required slug property: ${selectedPath}`);
      if (seen.has(slug)) throw new Error(`Selected document slug is duplicated: ${slug}`);
      seen.add(slug);
      slugs.push(slug);
    }
    return slugs;
  }

  function renderCandidates(note = "") {
    list.empty();
    const candidates = [...session.candidates.values()];
    const selectedCount = candidates.filter((item) => item.selected).length;
    status.setText(
      candidates.length
        ? `${candidates.length} candidate${candidates.length === 1 ? "" : "s"}; ${selectedCount} selected${note ? ` — ${note}` : ""}`
        : `No candidate files in this vault session${note ? ` — ${note}` : ""}`
    );
    for (const item of candidates) {
      const row = list.createEl("label");
      row.style.display = "flex";
      row.style.gap = "0.55em";
      row.style.alignItems = "baseline";
      const checkbox = row.createEl("input", { attr: { type: "checkbox" } });
      checkbox.checked = item.selected;
      checkbox.addEventListener("change", () => {
        item.selected = checkbox.checked;
        renderCandidates();
      });
      const text = row.createSpan();
      text.createEl("strong", { text: item.title });
      text.createSpan({ text: ` — ${item.path}` });
    }
  }

  async function addClipboardSelection() {
    try {
      const added = appendClipboardCandidates(app, session, await navigator.clipboard.readText());
      renderCandidates(added ? `added ${added} from clipboard` : "clipboard contained no new file references");
    } catch (error) {
      renderCandidates(`could not read clipboard: ${error.message || error}`);
    }
  }

  clearButton.addEventListener("click", () => {
    session.candidates.clear();
    renderCandidates("dispatch list cleared");
    notify("Dispatch list cleared.");
  });
  selectAllButton.addEventListener("click", () => {
    for (const item of session.candidates.values()) item.selected = true;
    renderCandidates();
    notify(`Selected all ${session.candidates.size} dispatch candidate(s).`);
  });
  selectNoneButton.addEventListener("click", () => {
    for (const item of session.candidates.values()) item.selected = false;
    renderCandidates();
    notify("Cleared dispatch selection.");
  });

  await addClipboardSelection();

  const snapshotResult = await serviceCall(app, "define-plan-snapshot", { version: 1 });
  const snapshot = JSON.parse(String(snapshotResult.stdout || "{}").trim() || "{}");
  if (!snapshot.ok) throw new Error(snapshot.error || "Could not load plans from the service");
  const plansByIdentity = new Map(Object.values(snapshot.server?.registries?.plans || {}).map((plan) => [String(plan.record_identity || plan.slug || ""), plan]));
  for (const plan of snapshot.authored_plans || []) plansByIdentity.set(String(plan.record_identity || plan.slug || ""), plan);
  const planRows = [...plansByIdentity.values()].filter((plan) => String(plan.record_identity || plan.slug || "").trim());
  if (!Array.isArray(planRows) || !planRows.length) {
    container.createEl("p", { text: "No plans are available." });
    return;
  }

  const form = container.createEl("div");
  form.style.display = "grid";
  form.style.gap = "0.6em";
  form.style.maxWidth = "42em";
  form.createEl("label", { text: "Plan" });
  const select = form.createEl("select");
  for (const plan of planRows) {
    const slug = String(plan.record_identity || plan.slug || "").trim();
    if (!slug) continue;
    select.createEl("option", { text: String(plan.payload?.title || plan.title || plan.payload?.label || plan.label || plan.name || slug), value: slug });
  }

  const combineRow = form.createEl("label");
  combineRow.style.display = "flex";
  combineRow.style.gap = "0.5em";
  combineRow.style.alignItems = "center";
  const combine = combineRow.createEl("input", { attr: { type: "checkbox" } });
  combineRow.createSpan({ text: "Combine selected files" });

  form.createEl("label", { text: "Combined record basename" });
  const combineBasename = form.createEl("input", {
    attr: { type: "text", placeholder: "Example: chapter-one", disabled: "disabled" }
  });
  combine.addEventListener("change", () => {
    combineBasename.disabled = !combine.checked;
    if (combine.checked) combineBasename.focus();
  });

  const runButton = form.createEl("button", { text: "Dispatch Run", cls: "mod-cta" });
  const result = container.createEl("pre");
  result.style.whiteSpace = "pre-wrap";

  runButton.addEventListener("click", async () => {
    notify("Running dispatch…");
    runButton.disabled = true;
    result.setText("Sending the document and plan slugs to the service…");
    try {
      const documents = selectedDocumentSlugs();
      if (!documents.length) {
        throw new Error("Select at least one candidate file.");
      }
      const basename = combineBasename.value.trim();
      if (combine.checked && !basename) {
        throw new Error("Enter a basename for the combined record.");
      }
      if (combine.checked) {
        throw new Error("Combined dispatch is not yet available through the service.");
      }
      const transport = await runDispatch(app, {
        documents,
        plan: select.value,
      });
      session.candidates.clear();
      renderCandidates("manifest cleared after dispatch");
      result.setText(
        `Dispatch uploaded and enqueued by the service.\n` +
        `Plan: ${transport.plan}\n` +
        `Records: ${transport.records}`
      );
    } catch (error) {
      console.error("Dispatch Run failed", error);
      const detail = String(error?.message || error || "Unknown dispatch error");
      result.setText(`Dispatch failed.\n${detail}`);
      notify(`Dispatch failed: ${detail}`);
    } finally {
      runButton.disabled = false;
    }
  });
}


module.exports = { renderDispatchRun };
