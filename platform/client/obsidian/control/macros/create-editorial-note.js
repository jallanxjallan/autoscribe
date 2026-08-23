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

module.exports = async function createEditorialNote(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const loader = createControlRuntime(app);
  const { notify } = loader.requireControl("scripts/lib/notify.js");
  const { titleCaseStem } = loader.requireControl("scripts/lib/text.js");
  const { normalizeVaultPath, ensureFolder } = loader.requireControl("scripts/lib/vault-files.js");
  const { readClipboardSelection } = loader.requireControl("scripts/lib/clipboard-selection.js");
  const { loadConfig } = loader.requireControl("scripts/lib/config-loader.js");
  const editorial = loadConfig("records").editorial_note || {};

  const input = await openDialog(editorial.dialog || {});
  if (!input) return;

  const title = titleCaseStem(input.title);
  if (!title) return notify("The title is blank.", 7000);

  const folderPath = normalizeVaultPath(editorial.folder);
  const filePath = normalizeVaultPath(`${folderPath}/${title}.md`);
  await ensureFolder(app, folderPath);

  if (app.vault.getAbstractFileByPath(filePath)) {
    return notify(`A note already exists at ${filePath}`, 7000);
  }

  let targets = [];
  if (input.useClipboard) {
    try {
      const rows = await readClipboardSelection(app);
      targets = [...new Set(rows.map((row) => row.path).filter(Boolean))];
      if (!targets.length) notify("No file targets were resolved from the clipboard.", 7000);
    } catch (error) {
      notify(`Clipboard targets skipped: ${error?.message || error}`, 8000);
    }
  }

  notify(`Creating ${title}…`);

  const yamlTargets = targets.length
    ? ["targets:", ...targets.map((target) => `  - \"[[${target.replace(/\.md$/i, "")}]]\"`)].join("\n")
    : "targets: []";

  const defaults = editorial.defaults || {};
  const content = [
    "---",
    `record: ${defaults.record}`,
    `action: ${input.action || defaults.action}`,
    `status: ${defaults.status}`,
    `created: ${new Date().toISOString().slice(0, 10)}`,
    yamlTargets,
    "---",
    "",
    `# ${title}`,
    "",
  ].join("\n");

  const file = await app.vault.create(filePath, content);
  await app.workspace.getLeaf(false).openFile(file, { active: true });
  notify(`Created ${title}`);
};

function openDialog(dialogConfig = {}) {
  return new Promise((resolve) => {
    let finished = false;

    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;z-index:var(--layer-modal,1000);display:grid;place-items:center;background:rgba(0,0,0,.45)";

    const dialog = document.createElement("div");
    dialog.className = "modal";
    dialog.style.cssText = "width:min(34rem,90vw);background:var(--background-primary);border:1px solid var(--background-modifier-border);border-radius:var(--radius-l);box-shadow:var(--shadow-l);padding:1rem";
    overlay.appendChild(dialog);

    dialog.createEl("h2", { text: String(dialogConfig.title) });

    const titleLabel = dialog.createEl("label", { text: "Title" });
    titleLabel.style.display = "block";
    const titleInput = titleLabel.createEl("input", { type: "text", placeholder: String(dialogConfig.title_placeholder) });
    titleInput.style.width = "100%";

    const actionLabel = dialog.createEl("label", { text: "Action" });
    actionLabel.style.cssText = "display:block;margin-top:.8rem";
    const actionInput = actionLabel.createEl("input", { type: "text", value: String(dialogConfig.action_default) });
    actionInput.style.width = "100%";

    const clipboardLabel = dialog.createEl("label");
    clipboardLabel.style.cssText = "display:flex;gap:.5rem;align-items:center;margin-top:.8rem";
    const clipboardInput = clipboardLabel.createEl("input", { type: "checkbox" });
    clipboardInput.checked = dialogConfig.clipboard_default !== false;
    clipboardLabel.createSpan({ text: "Use clipboard file selection as targets" });

    const buttons = dialog.createDiv();
    buttons.style.cssText = "display:flex;justify-content:flex-end;gap:.5rem;margin-top:1rem";
    const cancel = buttons.createEl("button", { text: "Cancel" });
    const create = buttons.createEl("button", { text: "Create", cls: "mod-cta" });

    function close(value) {
      if (finished) return;
      finished = true;
      document.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
      resolve(value);
    }

    function submit() {
      const title = titleInput.value.trim();
      if (!title) return titleInput.focus();
      close({ title, action: actionInput.value.trim() || String(dialogConfig.blank_action_fallback || ""), useClipboard: clipboardInput.checked });
    }

    function onKeyDown(event) {
      if (event.key === "Escape") close(null);
      if (event.key === "Enter" && event.target !== actionInput) {
        event.preventDefault();
        submit();
      }
    }

    cancel.onclick = () => close(null);
    create.onclick = submit;
    overlay.onmousedown = (event) => { if (event.target === overlay) close(null); };
    document.addEventListener("keydown", onKeyDown, true);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => titleInput.focus());
  });
}
