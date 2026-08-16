"use strict";

const path = require("node:path");

function loadAnnotations(app) {
  const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
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

async function choose(api, items, placeholder) {
  const selected = await api.suggester(
    items.map((item) => item.label),
    items.map((item) => item.id),
    false,
    placeholder
  );
  if (selected == null) return null;

  const value = String(selected);
  const byId = items.find((item) => item.id === value);
  if (byId) return byId.id;

  const byLabel = items.find((item) => item.label === value);
  return byLabel?.id || null;
}

async function requiredPrompt(api, label) {
  const value = await api.inputPrompt(label);
  if (value == null) return null;
  return value.trim() || null;
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
  const hasSelection = editor.somethingSelected();
  const availableTypes = hasSelection
    ? annotations.ANNOTATION_TYPES
    : annotations.ANNOTATION_TYPES.filter((item) => item.id !== "inline");
  const choiceId = await choose(quickAddApi, availableTypes, "Annotation type");
  if (!choiceId) return;

  let range;
  let replacement;

  switch (choiceId) {
    case "block": {
      const message = await requiredPrompt(quickAddApi, "Block message");
      if (!message) return;

      range = annotations.paragraphRange(editor);
      replacement = annotations.block(editor.getRange(range.from, range.to), message);
      break;
    }

    case "inline": {
      range = annotations.selectionRange(editor);
      if (!range) {
        new Notice("Select the text to annotate inline.");
        return;
      }

      const key = await choose(quickAddApi, annotations.INLINE_KEYS, "Inline key");
      if (!key) return;

      const message = await requiredPrompt(quickAddApi, "Inline message");
      if (!message) return;

      replacement = annotations.inline(
        editor.getRange(range.from, range.to),
        { key, message }
      );
      break;
    }

    case "directive": {
      const instruction = await requiredPrompt(quickAddApi, "Directive instruction");
      if (!instruction) return;

      const cursor = editor.getCursor() || { line: 0, ch: 0 };
      range = { from: cursor, to: cursor };
      replacement = annotations.directive(instruction);
      break;
    }

    default:
      throw new Error(`Unsupported annotation type: ${choiceId}`);
  }

  editor.replaceRange(replacement, range.from, range.to);

  const startOffset = editor.posToOffset(range.from);
  editor.setSelection(range.from, editor.offsetToPos(startOffset + replacement.length));
};
