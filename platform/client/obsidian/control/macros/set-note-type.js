"use strict";

/**
 * QuickAdd user script: Set Note Type
 *
 * Applies a configured note type to the active Markdown note. Creation and
 * movement are intentionally separate operations.
 */
module.exports = async function setNoteType(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const file = app.workspace.getActiveFile();
  if (!file || file.extension !== "md") {
    throw new Error("Set Note Type requires an active Markdown note.");
  }

  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const load = (relativePath) => nodeRequire(
    path.join(base, "_control", "scripts", ...relativePath.split("/"))
  );
  const { notify } = load("lib/notify.js");
  const { loadConfig } = load("lib/config-loader.js");
  const { applyTemplateToFile } = load("templates/apply-template-tools.js");

  const records = loadConfig("records");
  const groups = Object.entries(records.groups || {}).map(([id, group]) => ({
    id,
    label: group.label || id,
    initiallyOpen: Boolean(group.initially_open),
    choices: Object.entries(group.choices || {}).map(([choiceId, choice]) => ({
      id: choiceId,
      ...choice,
    })),
  }));

  const selection = await chooseType(groups, file.path);
  if (!selection) return;

  const editor = app.workspace.activeEditor?.editor || null;
  notify(`Setting note type: ${selection.choice.label}…`);

  try {
    const result = await applyTemplateToFile({
      app,
      targetPath: file.path,
      templatePath: selection.choice.template,
      slugPrefix: selection.choice.prefix,
      frontmatterOverrides: { ...(selection.choice.defaults || {}) },
      editor,
    });
    notify(`Set ${selection.choice.label}: ${result.path}`);
  } catch (error) {
    console.error("Set Note Type failed:", error);
    notify(`Set Note Type failed: ${error?.message || String(error)}`, 9000);
  }
};

function chooseType(groups, filePath) {
  return new Promise((resolve) => {
    let done = false;
    const style = document.createElement("style");
    style.textContent = `
      .set-type-overlay { position: fixed; inset: 0; z-index: var(--layer-modal, 1000); display: grid; place-items: center; background: rgba(0,0,0,.45); }
      .set-type-dialog { width: min(42rem, 90vw); max-height: 85vh; overflow: auto; background: var(--background-primary); color: var(--text-normal); border: 1px solid var(--background-modifier-border); border-radius: var(--radius-l); box-shadow: var(--shadow-l); padding: 1rem; }
      .set-type-dialog h2 { margin: 0 0 .25rem; }
      .set-type-path { margin: 0 0 1rem; color: var(--text-muted); font-family: var(--font-monospace); overflow-wrap: anywhere; }
      .set-type-groups { display: grid; gap: .55rem; }
      .set-type-group { border: 1px solid var(--background-modifier-border); border-radius: var(--radius-m); overflow: hidden; }
      .set-type-group summary { background: var(--background-secondary); cursor: pointer; font-weight: var(--font-semibold); padding: .75rem .9rem; }
      .set-type-choices { display: grid; gap: .5rem; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); padding: .75rem; }
      .set-type-choice { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 2.5rem; margin: 0; }
      .set-type-prefix { margin-left: .75rem; opacity: .65; font-family: var(--font-monospace); }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement("div");
    overlay.className = "set-type-overlay";
    const dialog = document.createElement("div");
    dialog.className = "set-type-dialog modal";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Set Note Type");
    overlay.appendChild(dialog);

    const heading = document.createElement("h2");
    heading.textContent = "Set Note Type";
    dialog.appendChild(heading);

    const pathLine = document.createElement("p");
    pathLine.className = "set-type-path";
    pathLine.textContent = filePath;
    dialog.appendChild(pathLine);

    const holder = document.createElement("div");
    holder.className = "set-type-groups";
    dialog.appendChild(holder);

    function close(value) {
      if (done) return;
      done = true;
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      style.remove();
      resolve(value);
    }

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
      }
    }

    for (const group of groups) {
      const details = document.createElement("details");
      details.className = "set-type-group";
      details.open = group.initiallyOpen;

      const summary = document.createElement("summary");
      summary.textContent = group.label;
      details.appendChild(summary);

      const choices = document.createElement("div");
      choices.className = "set-type-choices";
      details.appendChild(choices);

      for (const choice of group.choices) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "set-type-choice mod-cta";

        const label = document.createElement("span");
        label.textContent = choice.label || choice.id;
        button.appendChild(label);

        const prefix = document.createElement("span");
        prefix.className = "set-type-prefix";
        prefix.textContent = choice.prefix || "";
        button.appendChild(prefix);

        button.addEventListener("click", () => close({ group, choice }));
        choices.appendChild(button);
      }

      holder.appendChild(details);
    }

    overlay.addEventListener("mousedown", (event) => {
      if (event.target === overlay) close(null);
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(overlay);
  });
}
