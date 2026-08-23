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

let loadAnnotations;

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

async function annotateText({ app, quickAddApi }) {
  ({ loadAnnotations } = createControlRuntime(app).requireControl("scripts/lib/annotation-loader.js"));
  if (!quickAddApi?.suggester || !quickAddApi?.inputPrompt) {
    throw new Error("Annotate Text must be run as a QuickAdd macro.");
  }

  const editor = app.workspace.activeEditor?.editor;
  if (!editor) {
    throw new Error("Open a Markdown note in edit mode before running Annotate Text.");
  }

  const annotations = loadAnnotations();
  const range = annotations.selectionRange(editor);
  const selectedText = range
    ? editor.getRange(range.from, range.to)
    : "";

  if (!range || !selectedText.trim()) {
    new Notice("Select text to annotate.");
    return;
  }

  const key = await choose(quickAddApi, annotations.INLINE_KEYS, "Annotation key");
  if (!key) return;

  const message = await requiredPrompt(quickAddApi, "Annotation message");
  if (!message) return;

  const replacement = annotations.inline(selectedText, {
    key,
    message: `hm: ${message}`,
  });

  editor.replaceRange(replacement, range.from, range.to);

  const startOffset = editor.posToOffset(range.from);
  editor.setSelection(range.from, editor.offsetToPos(startOffset + replacement.length));
}

module.exports = annotateText;
