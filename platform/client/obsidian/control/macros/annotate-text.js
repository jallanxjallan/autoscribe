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

function cursorIsInFrontmatter(editor, cursor) {
  if (editor.getLine(0).trim() !== "---") return false;

  for (let line = 1; line < editor.lineCount(); line += 1) {
    if (editor.getLine(line).trim() === "---") return cursor.line <= line;
  }

  return true;
}

async function annotateText({ app, quickAddApi }) {
  if (!quickAddApi?.suggester || !quickAddApi?.inputPrompt) {
    throw new Error("Annotate Text must be run as a QuickAdd macro.");
  }

  const editor = app.workspace.activeEditor?.editor;
  if (!editor) {
    throw new Error("Open a Markdown note in edit mode before running Annotate Text.");
  }

  const annotations = loadAnnotations(app);
  let range;
  let replacement;

  const selectedRange = annotations.selectionRange(editor);
  const selectedText = selectedRange
    ? editor.getRange(selectedRange.from, selectedRange.to)
    : "";

  if (selectedRange && selectedText.trim()) {
    const key = await choose(quickAddApi, annotations.INLINE_KEYS, "Inline key");
    if (!key) return;

    const message = await requiredPrompt(quickAddApi, "Inline message");
    if (!message) return;

    range = selectedRange;
    replacement = annotations.inline(selectedText, { key, message });
  } else {
    const cursor = editor.getCursor() || { line: 0, ch: 0 };
    const cursorLine = editor.getLine(cursor.line);
    if (!cursorLine.trim() || cursorIsInFrontmatter(editor, cursor)) {
      new Notice("Place the cursor in a paragraph to add a block annotation.");
      return;
    }

    const key = await choose(quickAddApi, annotations.INLINE_KEYS, "Block key");
    if (!key) return;

    const message = await requiredPrompt(quickAddApi, "Block message");
    if (!message) return;

    range = annotations.paragraphRange(editor);
    replacement = annotations.block(
      editor.getRange(range.from, range.to),
      { key, message }
    );
  }

  editor.replaceRange(replacement, range.from, range.to);

  const startOffset = editor.posToOffset(range.from);
  editor.setSelection(range.from, editor.offsetToPos(startOffset + replacement.length));
}

module.exports = annotateText;
