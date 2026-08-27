"use strict";

/**
 * Shared Instructions State implementation.
 *
 * The active Instructions vault is the source of instruction files. Every explicit
 * instruction Markdown file is listed. The service supplies authoritative
 * server state and performs instruction synchronization. The UI neither
 * invokes `asc` nor inspects Git directly.
 */
module.exports = async function instructionsState(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const { serviceCall } = require("./lib/service-command.js");
  const { loadConfig } = require("./lib/config-loader.js");
  const path = require("node:path");
  const protocol = loadConfig("protocol");

  async function callService(spec, input = null) {
    const command = String(spec?.command || "");
    const requestVersion = Number(spec?.request_version);
    const response = await serviceCall(app, command, input || { version: requestVersion });
    const output = JSON.parse(String(response.stdout || "{}").trim() || "{}");
    if (!output.ok) throw new Error(output.error || `${command} failed`);
    return output;
  }

  function notify(message, timeout = 5000) {
    const text = String(message || "");
    const candidates = [
      globalThis?.Notice,
      globalThis?.window?.Notice,
    ];
    for (const NoticeClass of candidates) {
      try {
        if (typeof NoticeClass === "function") {
          new NoticeClass(text, timeout);
          return;
        }
      } catch (_) {}
    }

    // Last-resort visible toast for QuickAdd/user-script environments where
    // Obsidian's Notice constructor is not exposed globally.
    try {
      const toast = document.createElement("div");
      toast.textContent = text;
      toast.style.cssText = [
        "position:fixed",
        "right:1rem",
        "bottom:1rem",
        "z-index:100000",
        "max-width:min(36rem,80vw)",
        "padding:.7rem .9rem",
        "background:var(--background-secondary)",
        "color:var(--text-normal)",
        "border:1px solid var(--background-modifier-border)",
        "border-radius:var(--radius-m)",
        "box-shadow:var(--shadow-l)",
      ].join(";");
      document.body.append(toast);
      globalThis.setTimeout(() => toast.remove(), timeout);
      return;
    } catch (_) {}
    console.log(text);
  }

  async function readInstructionRows() {
    const spec = protocol.service_operations?.instructions_state_snapshot || {};
    const snapshot = await callService(spec);
    const items = Array.isArray(snapshot.items) ? snapshot.items : [];
    return items.map((item) => {
      const identity = String(item?.slug || item?.record_identity || item?.key || "").trim();
      const relativePath = String(item?.relative_path || item?.path || "").trim();
      const remote = String(item?.remote || "missing");
      const needsUpload = Boolean(item?.needs_upload);
      return {
        identity,
        title: String(item?.title || identity).trim() || identity,
        filename: relativePath ? path.posix.basename(relativePath) : `${identity}.md`,
        relativePath,
        scope: String(item?.scope || "").trim(),
        component: String(item?.component || "").trim(),
        remote,
        needsUpload,
        syncStatus: String(item?.status || "").trim(),
        remoteDetail: remote === "present"
          ? `Server record present: ${identity}`
          : `Server record missing: ${identity}`,
      };
    }).filter((row) => row.identity && row.relativePath);
  }

  async function uploadInstructions(rows) {
    if (!rows.length) throw new Error("No instruction files selected.");
    const syncSpec = protocol.service_operations?.instructions_sync || {};
    const result = await callService(syncSpec, {
      version: Number(syncSpec.request_version),
      slugs: rows.map((row) => row.identity),
    });
    return { records: rows, result };
  }

  // Dashboard and other read-only Instructions views consume the same snapshot.
  if (params.mode === "snapshot") return readInstructionRows();


  return new Promise((resolve) => {
    let closed = false;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;z-index:var(--layer-modal,1000);display:grid;place-items:center;background:rgba(0,0,0,.48);padding:2vh 2vw;";
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Instructions State");
    dialog.style.cssText = "width:min(96vw,76rem);max-height:96vh;overflow:auto;background:var(--background-primary);color:var(--text-normal);border:1px solid var(--background-modifier-border);border-radius:var(--radius-l);box-shadow:var(--shadow-l);padding:1rem;";

    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1rem;position:sticky;top:-1rem;background:var(--background-primary);z-index:3;padding:.25rem 0 .65rem;";
    const heading = document.createElement("h2");
    heading.textContent = "Instructions State";
    heading.style.margin = "0";
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "Close";
    header.append(heading, closeButton);

    const container = document.createElement("div");
    dialog.append(header, container);
    overlay.append(dialog);
    document.body.append(overlay);

    function close(value = null) {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
      resolve(value);
    }
    function onKeyDown(event) {
      if (event.key === "Escape") { event.preventDefault(); close(); }
    }
    closeButton.onclick = () => close();
    overlay.addEventListener("mousedown", (event) => { if (event.target === overlay) close(); });
    document.addEventListener("keydown", onKeyDown, true);

    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.8rem;";
    const refreshButton = document.createElement("button");
    refreshButton.type = "button";
    refreshButton.textContent = "Refresh";
    const selectNeededButton = document.createElement("button");
    selectNeededButton.type = "button";
    selectNeededButton.textContent = "Select Upload Needed";
    const selectAllButton = document.createElement("button");
    selectAllButton.type = "button";
    selectAllButton.textContent = "Select All";
    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.textContent = "Clear";
    const uploadButton = document.createElement("button");
    uploadButton.type = "button";
    uploadButton.textContent = "Upload";
    uploadButton.classList.add("mod-cta");
    toolbar.append(refreshButton, selectNeededButton, selectAllButton, clearButton, uploadButton);
    container.append(toolbar);

    const summary = document.createElement("div");
    summary.style.cssText = "margin:.4rem 0 .7rem;color:var(--text-muted);";
    const list = document.createElement("div");
    list.style.cssText = "border:1px solid var(--background-modifier-border);border-radius:var(--radius-m);max-height:58vh;overflow:auto;padding:.35rem;";
    const output = document.createElement("pre");
    output.style.cssText = "white-space:pre-wrap;max-height:18rem;overflow:auto;margin-top:.8rem;";
    container.append(summary, list, output);

    let rows = [];
    let boxes = [];

    function uploadNeeded(row) {
      return row.needsUpload;
    }

    function updateSummary() {
      const selected = boxes.filter((box) => box?.checked).length;
      const missing = rows.filter((row) => row.remote === "missing").length;
      summary.textContent = `${rows.length} instruction(s) · ${missing} server missing · ${selected} selected`;
      uploadButton.disabled = selected === 0;
    }

    function stateText(row) {
      if (row.remote === "missing") return "missing";
      if (row.needsUpload) return "dirty";
      return "current";
    }

    function renderRows() {
      list.replaceChildren();
      boxes = [];

      const groups = new Map();
      rows.forEach((row, index) => {
        const folder = path.posix.dirname(row.relativePath) === "." ? "Vault root" : path.posix.dirname(row.relativePath);
        if (!groups.has(folder)) groups.set(folder, []);
        groups.get(folder).push({ row, index });
      });

      for (const [folder, items] of groups) {
        const section = document.createElement("section");
        section.style.cssText = "margin:.25rem 0 .7rem;border:1px solid var(--background-modifier-border);border-radius:var(--radius-m);overflow:hidden;";

        const folderHeading = document.createElement("div");
        folderHeading.style.cssText = "display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:1rem;padding:.55rem .75rem;background:var(--background-secondary);font-weight:600;position:sticky;top:0;z-index:2;";
        const folderName = document.createElement("span");
        folderName.textContent = folder;
        const folderCount = document.createElement("span");
        const folderNeeded = items.filter(({ row }) => uploadNeeded(row)).length;
        folderCount.textContent = `${items.length} instruction${items.length === 1 ? "" : "s"}${folderNeeded ? ` · ${folderNeeded} need upload` : ""}`;
        folderCount.style.cssText = "font-size:var(--font-ui-smaller);font-weight:400;color:var(--text-muted);";
        folderHeading.append(folderName, folderCount);
        section.append(folderHeading);

        const columnHeading = document.createElement("div");
        columnHeading.style.cssText = "display:grid;grid-template-columns:1.6rem 10.5rem minmax(0,1fr);gap:.7rem;align-items:center;padding:.35rem .7rem;color:var(--text-muted);font-size:var(--font-ui-smaller);border-top:1px solid var(--background-modifier-border);border-bottom:1px solid var(--background-modifier-border);";
        columnHeading.append(document.createElement("span"), Object.assign(document.createElement("span"), { textContent: "State" }), Object.assign(document.createElement("span"), { textContent: "Instruction" }));
        section.append(columnHeading);

        items.forEach(({ row, index: rowIndex }, itemIndex) => {
          const label = document.createElement("label");
          label.style.cssText = `display:grid;grid-template-columns:1.6rem 10.5rem minmax(0,1fr);gap:.7rem;align-items:center;padding:.5rem .7rem;cursor:pointer;${itemIndex ? "border-top:1px solid var(--background-modifier-border);" : ""}`;

          const box = document.createElement("input");
          box.type = "checkbox";
          box.dataset.rowIndex = String(rowIndex);
          box.addEventListener("change", updateSummary);
          boxes[rowIndex] = box;

          const state = document.createElement("code");
          state.textContent = stateText(row);
          state.style.cssText = "font-size:var(--font-ui-smaller);color:var(--text-muted);white-space:nowrap;";
          state.title = row.remoteDetail || stateText(row);

          const file = document.createElement("a");
          const linkTarget = row.relativePath.replace(/\.md$/i, "");
          file.classList.add("internal-link");
          file.dataset.href = linkTarget;
          file.href = linkTarget;
          file.style.cssText = "min-width:0;overflow-wrap:anywhere;";
          file.textContent = `[[${path.posix.basename(linkTarget)}]]`;
          file.title = `${row.relativePath}\n${row.identity}`;
          file.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            void app.workspace.openLinkText(linkTarget, "", false);
          });

          label.append(box, state, file);
          section.append(label);
        });
        list.append(section);
      }

      if (!rows.length) {
        const empty = document.createElement("div");
        empty.textContent = "No instruction files found in the active vault.";
        empty.style.cssText = "padding:1rem;text-align:center;color:var(--text-muted);";
        list.append(empty);
      }
      updateSummary();
    }

    async function refresh({ announce = true } = {}) {
      if (announce) notify("Refreshing Instructions State…", 3000);
      refreshButton.disabled = true;
      selectNeededButton.disabled = true;
      selectAllButton.disabled = true;
      uploadButton.disabled = true;
      output.textContent = "Reading instruction state from service…";
      try {
        rows = await readInstructionRows();
        output.textContent = "";
        renderRows();
        if (announce) notify(`Instructions State refreshed: ${rows.length} instruction(s).`, 5000);
      } catch (error) {
        rows = [];
        renderRows();
        output.textContent = error?.stack || error?.message || String(error);
        notify(`Instructions State failed: ${error?.message || error}`, 9000);
      } finally {
        refreshButton.disabled = false;
        selectNeededButton.disabled = false;
        selectAllButton.disabled = false;
        updateSummary();
      }
    }

    refreshButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void refresh({ announce: true });
    });
    selectNeededButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      rows.forEach((row, index) => { if (boxes[index]) boxes[index].checked = uploadNeeded(row); });
      updateSummary();
    });
    selectAllButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      boxes.forEach((box) => { if (box) box.checked = true; });
      updateSummary();
    });
    clearButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      boxes.forEach((box) => { if (box) box.checked = false; });
      updateSummary();
    });
    uploadButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const selected = rows.filter((_, index) => boxes[index]?.checked);
      if (!selected.length) {
        notify("No instructions selected for upload.", 5000);
        output.textContent = "No instructions selected for upload.";
        return;
      }

      const originalLabel = uploadButton.textContent;
      const startMessage = `Uploading ${selected.length} instruction${selected.length === 1 ? "" : "s"}…`;
      uploadButton.textContent = startMessage;
      uploadButton.disabled = true;
      refreshButton.disabled = true;
      selectNeededButton.disabled = true;
      selectAllButton.disabled = true;
      clearButton.disabled = true;
      output.textContent = startMessage;
      notify(startMessage, 5000);
      console.info(`[Instructions State] ${startMessage}`);

      // Give Obsidian a paint cycle before spawning the CLI. If the button
      // text and notice appear, we know the click handler itself fired.
      await new Promise((resolveTick) => globalThis.setTimeout(resolveTick, 0));

      try {
        const outcome = await uploadInstructions(selected);
        const doneMessage = `Upload completed for ${outcome.records.length} selected instruction(s).`;
        output.textContent = [
          doneMessage,
          Array.isArray(outcome.result?.items) ? `\nService results:\n${outcome.result.items.map((item) => `${item.slug}: ${item.status}`).join("\n")}` : "",
        ].filter(Boolean).join("\n");
        notify(doneMessage, 7000);
        console.info(`[Instructions State] ${doneMessage}`);
        rows = await readInstructionRows();
        renderRows();
      } catch (error) {
        const failure = `Upload failed: ${error?.message || error}`;
        output.textContent = error?.stack || error?.message || String(error);
        notify(failure, 10000);
        console.error("[Instructions State]", error);
      } finally {
        uploadButton.textContent = originalLabel;
        refreshButton.disabled = false;
        selectNeededButton.disabled = false;
        selectAllButton.disabled = false;
        clearButton.disabled = false;
        updateSummary();
      }
    });

    refresh({ announce: false });
  });
};
