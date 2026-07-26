"use strict";

/*
 * QuickAdd user script for creating a typed note from an existing template.
 * Uses only the app object, browser DOM, and existing vault-local helpers.
 */

const NOTE_GROUPS = [
  {
    label: "Content",
    folder: "Content",
    initiallyOpen: true,
    choices: [
      { label: "Passage", class: "passage", prefix: "psg", template: "_control/templates/content/content.md" },
      { label: "Caption", class: "caption", prefix: "cap", template: "_control/templates/content/content.md" },
      { label: "Sidebar", class: "sidebar", prefix: "sdb", template: "_control/templates/content/content.md" },
      { label: "Epigraph", class: "epigraph", prefix: "epi", template: "_control/templates/content/content.md" },
    ],
  },
  {
    label: "Materials",
    folder: "Materials",
    initiallyOpen: true,
    choices: [
      { label: "Topic", class: "topic", prefix: "tpc", template: "_control/templates/reference/topic.md" },
      { label: "Finding", class: "finding", prefix: "fnd", template: "_control/templates/reference/finding.md" },
    ],
  },
  {
    label: "Instructions",
    folder: "Instructions",
    initiallyOpen: false,
    choices: [
      { label: "Role", class: "role", prefix: "rol", template: "_control/templates/instructions/role.md" },
      { label: "Context", class: "context", prefix: "cxt", template: "_control/templates/instructions/context.md" },
      { label: "Reference", class: "reference", prefix: "ref", template: "_control/templates/instructions/reference.md" },
      { label: "Instruction", class: "instruction", prefix: "ins", template: "_control/templates/instructions/instruction.md" },
    ],
  },
];

function getNodeRequire() {
  if (typeof require === "function") return require;
  if (typeof window !== "undefined" && typeof window.require === "function") {
    return window.require;
  }
  throw new Error("Node require is unavailable in this Obsidian context.");
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;
  if (typeof adapter?.getBasePath === "function") return adapter.getBasePath();
  if (adapter?.basePath) return adapter.basePath;
  throw new Error("Could not determine vault base path.");
}

function requireFromVault(app, vaultRelativePath) {
  const nodeRequire = getNodeRequire();
  const path = nodeRequire("node:path");
  const fullPath = path.join(
    getVaultBasePath(app),
    ...String(vaultRelativePath || "").split("/").filter(Boolean),
  );

  // QuickAdd may expose a callable require without Node's resolve/cache
  // properties. Requiring the absolute path works in both cases.
  if (nodeRequire.cache?.[fullPath]) {
    delete nodeRequire.cache[fullPath];
  }

  return nodeRequire(fullPath);
}

function normalizeVaultPath(value) {
  return String(value || "")
    .replace(/\\/g, "/")
    .replace(/^\/+|\/+$/g, "")
    .replace(/\/{2,}/g, "/");
}

function isFolder(item) {
  return Boolean(item && Array.isArray(item.children));
}

module.exports = async function createTypedNote(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) {
    throw new Error("Obsidian app object unavailable.");
  }

  const { notify } = requireFromVault(app, "_control/scripts/lib/notify.js");
  const { titleCaseStem, kebabCase } = requireFromVault(app, "_control/scripts/lib/text.js");
  const { applyTemplateToFile } = requireFromVault(
    app,
    "_control/scripts/templates/apply-template-tools.js"
  );

  const selection = await openTypedNoteDialog({ titleCaseStem, kebabCase });
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

  try {
    file = await app.vault.create(filePath, "");

    await applyTemplateToFile({
      app,
      targetPath: file.path,
      templatePath: selection.choice.template,
      slugPrefix: selection.choice.prefix,
      frontmatterOverrides: { class: selection.choice.class },
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

    console.error("Create Typed Note failed:", error);
    notify(`Create Typed Note failed: ${error?.message || String(error)}`, 9000);
  }
};

function openTypedNoteDialog({ titleCaseStem, kebabCase }) {
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
    dialog.setAttribute("aria-label", "Create Typed Note");
    overlay.appendChild(dialog);

    const heading = document.createElement("h2");
    heading.textContent = "Create Typed Note";
    dialog.appendChild(heading);

    const intro = document.createElement("p");
    intro.className = "typed-note-intro";
    intro.textContent = "Enter a title, then choose the template class.";
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

    for (const group of NOTE_GROUPS) {
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

async function ensureFolder(app, folderPath) {
  const normalized = normalizeVaultPath(folderPath);
  const existing = app.vault.getAbstractFileByPath(normalized);

  if (isFolder(existing)) return;
  if (existing) throw new Error(`A file already occupies ${normalized}.`);

  const parts = normalized.split("/").filter(Boolean);
  let current = "";

  for (const part of parts) {
    current = current ? `${current}/${part}` : part;
    const item = app.vault.getAbstractFileByPath(current);
    if (isFolder(item)) continue;
    if (item) throw new Error(`A file already occupies ${current}.`);
    await app.vault.createFolder(current);
  }
}
