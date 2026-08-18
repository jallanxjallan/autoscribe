"use strict";

const path = require("node:path");

function loadAnnotations(app) {
  const vaultRoot =
    app.vault.adapter.getBasePath?.() ||
    app.vault.adapter.basePath;

  const modulePath = path.join(
    vaultRoot,
    "_control",
    "scripts",
    "lib",
    "annotate.js"
  );
  const electronRequire = globalThis.window?.require;

  if (electronRequire?.cache && electronRequire?.resolve) {
    delete electronRequire.cache[electronRequire.resolve(modulePath)];
    return electronRequire(modulePath);
  }

  return require(modulePath);
}

function compareText(a, b) {
  return String(a).localeCompare(String(b), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function compareAnnotations(a, b) {
  return (
    compareText(a.title, b.title) ||
    a.line - b.line ||
    compareText(a.text, b.text)
  );
}

function compareTypes(a, b, typeOrder = []) {
  const aIndex = typeOrder.indexOf(a);
  const bIndex = typeOrder.indexOf(b);
  if (aIndex < 0 && bIndex < 0) return compareText(a, b);
  if (aIndex < 0) return 1;
  if (bIndex < 0) return -1;
  return aIndex - bIndex;
}

async function openAtLine(app, item) {
  const file = app.vault.getAbstractFileByPath(item.path);

  if (!file) {
    throw new Error(
      `Annotated file not found: ${item.path}`
    );
  }

  const leaf = app.workspace.getLeaf(false);
  await leaf.openFile(file);

  const editor = app.workspace.activeEditor?.editor;
  if (!editor) return;

  const line = Math.max(0, item.line - 1);
  const ch = 0;

  editor.setCursor({ line, ch });

  editor.scrollIntoView(
    {
      from: { line, ch: 0 },
      to: {
        line,
        ch: editor.getLine(line).length,
      },
    },
    true
  );
}

function createInternalLink(
  container,
  app,
  item,
  close
) {
  const link = container.createEl("a", {
    cls: "internal-link",
    text: item.title,
    href: item.path,
    attr: {
      "data-href": item.path,
    },
  });

  link.addEventListener("click", async (event) => {
    event.preventDefault();
    close();
    await openAtLine(app, item);
  });
}

function showAnnotationList(app, found, typeOrder = []) {
  const container = document.body.createDiv({
    cls: "modal-container mod-dim",
  });

  const background = container.createDiv({
    cls: "modal-bg",
  });

  const modal = container.createDiv({
    cls: "modal",
  });

  const closeButton = modal.createDiv({
    cls: "modal-close-button",
  });

  const contentEl = modal.createDiv({
    cls: "modal-content autoscribe-annotations",
  });

  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  closeButton.setAttribute("aria-label", "Close");

  contentEl.createEl("h2", {
    text: `Annotations (${found.length})`,
  });

  const close = () => {
    document.removeEventListener(
      "keydown",
      onKeydown
    );

    container.remove();
  };

  const onKeydown = (event) => {
    if (event.key === "Escape") {
      close();
    }
  };

  background.addEventListener("click", close);
  closeButton.addEventListener("click", close);
  document.addEventListener("keydown", onKeydown);

  const grouped = new Map();

  for (const item of found) {
    if (!grouped.has(item.type)) {
      grouped.set(item.type, []);
    }

    grouped.get(item.type).push(item);
  }

  const types = [...grouped.keys()].sort(
    (a, b) => compareTypes(a, b, typeOrder)
  );

  for (const type of types) {
    const items = grouped
      .get(type)
      .sort(compareAnnotations);

    const details = contentEl.createEl("details");
    const summary = details.createEl("summary");

    summary.createEl("strong", {
      text: `${type} (${items.length})`,
    });

    const table = details.createEl("table");
    const head = table
      .createEl("thead")
      .createEl("tr");

    head.createEl("th", { text: "Note" });
    head.createEl("th", {
      text: "Annotation",
    });

    const body = table.createEl("tbody");

    for (const item of items) {
      const row = body.createEl("tr");
      const noteCell = row.createEl("td");

      createInternalLink(
        noteCell,
        app,
        item,
        close
      );

      noteCell.createEl("small", {
        text: ` · line ${item.line}`,
      });

      row.createEl("td", {
        text: item.text,
      });
    }
  }
}

module.exports = async ({ app }) => {
  const annotations = loadAnnotations(app);
  const found =
    await annotations.collectAnnotations(app);

  if (!found.length) {
    new Notice("No annotations found.");
    return;
  }

  showAnnotationList(app, found, annotations.ANNOTATION_TYPES.map((item) => item.label));
};
