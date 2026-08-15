"use strict";

const path = require("node:path");

function loadAnnotations(app) {
  const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  return require(path.join(vaultRoot, "_control", "scripts", "lib", "annotations.js"));
}

async function choose(api, items, placeholder) {
  const selected = await api.suggester(
    items.map((item) => item.label),
    items,
    false,
    placeholder
  );
  return selected || null;
}

async function prompt(api, label, defaultValue = "") {
  const value = await api.inputPrompt(label, undefined, defaultValue);
  return value == null ? null : value;
}

module.exports = async ({ app, quickAddApi }) => {
  if (!quickAddApi?.suggester || !quickAddApi?.inputPrompt) {
    throw new Error("Annotate Text must be run as a QuickAdd macro.");
  }

  const editor = app.workspace.activeEditor?.editor;
  if (!editor) {
    throw new Error("Open a Markdown note in edit mode before running Annotate Text.");
  }

  const annotations = loadAnnotations(app);
  const choice = await choose(
    quickAddApi,
    annotations.ANNOTATION_TYPES,
    "Annotation type"
  );
  if (!choice) return;

  const range = annotations.targetRange(editor);
  const target = editor.getRange(range.from, range.to);
  let replacement;

  switch (choice.id) {
    case "callout": {
      const type = await prompt(quickAddApi, "Callout type");
      if (type == null || !type.trim()) return;

      const summary = await prompt(quickAddApi, "First line / summary (optional)");
      if (summary == null) return;

      const note = await prompt(quickAddApi, "Note text (optional)");
      if (note == null) return;

      replacement = annotations.callout(target, { type, summary, note });
      break;
    }

    case "highlight": {
      const span = await prompt(
        quickAddApi,
        "Exact span to highlight (leave blank for the whole target)",
        editor.somethingSelected() ? target : ""
      );
      if (span == null) return;
      replacement = annotations.highlight(target, span);
      break;
    }

    case "ai-highlight": {
      const type = await prompt(quickAddApi, "AI annotation type");
      if (type == null || !type.trim()) return;

      const span = await prompt(
        quickAddApi,
        "Exact span to highlight (leave blank for the whole target)",
        editor.somethingSelected() ? target : ""
      );
      if (span == null) return;

      replacement = annotations.aiHighlight(target, { type, span });
      break;
    }

    case "tk": {
      const note = await prompt(quickAddApi, "TK note (optional)");
      if (note == null) return;
      replacement = annotations.tk(target, note);
      break;
    }

    default:
      throw new Error(`Unsupported annotation type: ${choice.id}`);
  }

  editor.replaceRange(replacement, range.from, range.to);

  const startOffset = editor.posToOffset(range.from);
  editor.setSelection(
    range.from,
    editor.offsetToPos(startOffset + replacement.length)
  );
};
