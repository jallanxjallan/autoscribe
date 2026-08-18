"use strict";

/*
 * QuickAdd user script for creating a note from an existing template.
 * Uses only the app object, browser DOM, and existing vault-local helpers.
 */


module.exports = async function createNote(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) {
    throw new Error("Obsidian app object unavailable.");
  }

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const load = (relativePath) => nodeRequire(
    path.join(base, "_control", "scripts", ...relativePath.split("/"))
  );
  const { notify } = load("lib/notify.js");
  const { titleCaseStem, kebabCase } = load("lib/text.js");
  const { normalizeVaultPath, ensureFolder } = load("lib/vault-files.js");
  const { applyTemplateToFile } = load("templates/apply-template-tools.js");
  const { loadConfig } = load("lib/config-loader.js");
  const recordConfig = loadConfig("records");
  const noteGroups = Object.entries(recordConfig.groups || {}).map(([id, group]) => ({
    id, ...group,
    initiallyOpen: Boolean(group.initially_open),
    choices: Object.entries(group.choices || {}).map(([choiceId, choice]) => ({ id: choiceId, ...choice })),
  }));

  const selection = await openCreateNoteDialog({ titleCaseStem, kebabCase, noteGroups });
  if (!selection) return;

  const title = titleCaseStem(selection.rawTitle);
  if (!title) {
    notify("The title is blank.", 7000);
    return;
  }

  const folderPath = normalizeVaultPath(selection.group.folder);
  const filePath = normalizeVaultPath(`${folderPath}/${title}.md`);

  await ensureFolder(app, folderPath);

  if (app.vault.getAbstractFileByPath(filePath)) {
    notify(`A note already exists at ${filePath}`, 7000);
    return;
  }

  let file = null;

  notify(`Creating ${title}…`);

  try {
    file = await app.vault.create(filePath, "");

    await applyTemplateToFile({
      app,
      targetPath: file.path,
      templatePath: selection.choice.template,
      slugPrefix: selection.choice.prefix,
      frontmatterOverrides: { ...(selection.choice.defaults || {}) },
    });

    await app.workspace.getLeaf(false).openFile(file, { active: true });
    notify(`Created ${title}`);
  } catch (error) {
    if (file && app.vault.getAbstractFileByPath(file.path)) {
      try {
        await app.vault.delete(file, true);
      } catch (cleanupError) {
        console.error("Could not remove incomplete note:", cleanupError);
      }
    }

    console.error("Create Note failed:", error);
    notify(`Create Note failed: ${error?.message || String(error)}`, 9000);
  }
};

function openCreateNoteDialog({ titleCaseStem, kebabCase, noteGroups }) {
  return new Promise((resolve) => {
    let finished = false;

    const style = document.createElement("style");
    style.textContent = `
      .typed-note-overlay {
        position: fixed; inset: 0; z-index: var(--layer-modal, 1000);
        display: grid; place-items: center;
        background: rgba(0, 0, 0, .45);
      }
      .typed-note-dialog {
        width: min(42rem, 90vw); max-height: 85vh; overflow: auto;
        background: var(--background-primary); color: var(--text-normal);
        border: 1px solid var(--background-modifier-border);
        border-radius: var(--radius-l); box-shadow: var(--shadow-l);
        padding: 1rem;
      }
      .typed-note-dialog h2 { margin: 0 0 .35rem; }
      .typed-note-intro { color: var(--text-muted); margin: 0 0 1rem; }
      .typed-note-label { display: block; font-weight: var(--font-semibold); margin-bottom: .35rem; }
      .typed-note-input { width: 100%; }
      .typed-note-preview {
        background: var(--background-secondary); border-radius: var(--radius-s);
        color: var(--text-muted); font-family: var(--font-monospace);
        margin: .75rem 0 1rem; overflow-wrap: anywhere; padding: .65rem .8rem;
      }
      .typed-note-groups { display: grid; gap: .55rem; }
      .typed-note-group {
        border: 1px solid var(--background-modifier-border);
        border-radius: var(--radius-m); overflow: hidden;
      }
      .typed-note-group summary {
        background: var(--background-secondary); cursor: pointer;
        font-weight: var(--font-semibold); padding: .75rem .9rem;
      }
      .typed-note-choices {
        display: grid; gap: .5rem;
        grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
        padding: .75rem;
      }
      .typed-note-choice {
        align-items: center; display: flex; justify-content: space-between;
        margin: 0; min-height: 2.5rem; width: 100%;
      }
      .typed-note-prefix { font-family: var(--font-monospace); margin-left: .75rem; opacity: .72; }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement("div");
    overlay.className = "typed-note-overlay";

    const dialog = document.createElement("div");
    dialog.className = "typed-note-dialog modal";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Create Note");
    overlay.appendChild(dialog);

    const heading = document.createElement("h2");
    heading.textContent = "Create Note";
    dialog.appendChild(heading);

    const intro = document.createElement("p");
    intro.className = "typed-note-intro";
    intro.textContent = "Enter a title, then choose the record type.";
    dialog.appendChild(intro);

    const label = document.createElement("label");
    label.className = "typed-note-label";
    label.textContent = "Title";
    dialog.appendChild(label);

    const input = document.createElement("input");
    input.className = "typed-note-input";
    input.type = "text";
    input.placeholder = "Quality in Diversity";
    label.appendChild(input);

    const preview = document.createElement("div");
    preview.className = "typed-note-preview";
    dialog.appendChild(preview);

    const groups = document.createElement("div");
    groups.className = "typed-note-groups";
    dialog.appendChild(groups);

    const buttons = [];

    function close(value) {
      if (finished) return;
      finished = true;
      document.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
      style.remove();
      resolve(value);
    }

    function updatePreview() {
      const rawTitle = input.value;
      const enabled = Boolean(rawTitle.trim());
      for (const button of buttons) button.disabled = !enabled;

      if (!enabled) {
        preview.textContent = "Filename: —    Slug hint: —";
        return;
      }

      const title = titleCaseStem(rawTitle);
      const hint = kebabCase(title, { fallback: "untitled", maxLength: 0 });
      preview.textContent = `Filename: ${title}.md    Slug hint: ${hint}`;
    }

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
      }
    }

    for (const group of noteGroups) {
      const details = document.createElement("details");
      details.className = "typed-note-group";
      details.open = Boolean(group.initiallyOpen);

      const summary = document.createElement("summary");
      summary.textContent = group.label;
      details.appendChild(summary);

      const choices = document.createElement("div");
      choices.className = "typed-note-choices";
      details.appendChild(choices);

      for (const choice of group.choices) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "mod-cta typed-note-choice";
        button.disabled = true;

        const text = document.createElement("span");
        text.textContent = choice.label;
        button.appendChild(text);

        const prefix = document.createElement("span");
        prefix.className = "typed-note-prefix";
        prefix.textContent = `${choice.prefix}.`;
        button.appendChild(prefix);

        button.addEventListener("click", () => {
          if (!input.value.trim()) {
            input.focus();
            return;
          }
          close({ rawTitle: input.value, group, choice });
        });

        choices.appendChild(button);
        buttons.push(button);
      }

      groups.appendChild(details);
    }

    input.addEventListener("input", updatePreview);
    overlay.addEventListener("mousedown", (event) => {
      if (event.target === overlay) close(null);
    });
    document.addEventListener("keydown", onKeyDown, true);
    document.body.appendChild(overlay);

    updatePreview();
    requestAnimationFrame(() => input.focus());
  });
}
