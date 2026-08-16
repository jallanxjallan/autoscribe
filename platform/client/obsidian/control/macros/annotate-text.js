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

function frontmatterEndLine(editor) {
  if (editor.getLine(0).trim() !== "---") return -1;

  for (let line = 1; line < editor.lineCount(); line += 1) {
    if (editor.getLine(line).trim() === "---") return line;
  }

  return -1;
}

function directiveContext(editor) {
  const cursor = editor.getCursor() || { line: 0, ch: 0 };
  const offset = editor.posToOffset(cursor);
  const endLine = frontmatterEndLine(editor);

  return {
    cursor,
    endLine,
    isDirective: offset === 0 || (endLine >= 0 && cursor.line <= endLine),
  };
}

function directiveInsertion(editor, context) {
  if (context.endLine < 0) {
    return {
      range: { from: context.cursor, to: context.cursor },
      prefix: "",
      suffix: "\n\n",
    };
  }

  const nextLine = context.endLine + 1;
  if (nextLine < editor.lineCount()) {
    const point = { line: nextLine, ch: 0 };
    return {
      range: { from: point, to: point },
      prefix: "",
      suffix: "\n\n",
    };
  }

  const point = {
    line: context.endLine,
    ch: editor.getLine(context.endLine).length,
  };
  return {
    range: { from: point, to: point },
    prefix: "\n\n",
    suffix: "",
  };
}

function promptDirective() {
  return new Promise((resolve) => {
    let finished = false;
    const overlay = document.body.createDiv({ cls: "modal-container mod-dim" });
    const background = overlay.createDiv({ cls: "modal-bg" });
    const modal = overlay.createDiv({ cls: "modal" });
    const closeButton = modal.createDiv({ cls: "modal-close-button" });
    const content = modal.createDiv({ cls: "modal-content" });

    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", "Directive instruction");
    closeButton.setAttribute("aria-label", "Cancel");

    content.createEl("h2", { text: "Directive" });
    const textarea = content.createEl("textarea", {
      attr: {
        rows: "10",
        placeholder: "Enter the directive. Enter creates a new line.",
      },
    });
    textarea.style.width = "100%";
    textarea.style.resize = "vertical";

    const buttons = content.createDiv();
    buttons.style.cssText = "display:flex;justify-content:flex-end;gap:.5rem;margin-top:1rem";
    const cancelButton = buttons.createEl("button", { text: "Cancel" });
    const saveButton = buttons.createEl("button", { text: "Set Directive", cls: "mod-cta" });

    function close(value) {
      if (finished) return;
      finished = true;
      document.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
      resolve(value);
    }

    function save() {
      const value = textarea.value.trim();
      if (!value) {
        textarea.focus();
        return;
      }
      close(value);
    }

    function onKeyDown(event) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      close(null);
    }

    background.addEventListener("click", () => close(null));
    closeButton.addEventListener("click", () => close(null));
    cancelButton.addEventListener("click", () => close(null));
    saveButton.addEventListener("click", save);
    document.addEventListener("keydown", onKeyDown, true);
    requestAnimationFrame(() => textarea.focus());
  });
}

async function annotateText({ app, quickAddApi, directivePrompt = promptDirective }) {
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
    const context = directiveContext(editor);

    if (context.isDirective) {
      const instruction = await directivePrompt();
      if (!instruction?.trim()) return;

      const insertion = directiveInsertion(editor, context);
      range = insertion.range;
      replacement = `${insertion.prefix}${annotations.directive(instruction)}${insertion.suffix}`;
    } else {
      const cursorLine = editor.getLine(context.cursor.line);
      if (!cursorLine.trim()) {
        new Notice("Place the cursor in a paragraph, at the start of the note, or in its frontmatter.");
        return;
      }

      const message = await requiredPrompt(quickAddApi, "Block message");
      if (!message) return;

      range = annotations.paragraphRange(editor);
      replacement = annotations.block(editor.getRange(range.from, range.to), message);
    }
  }

  editor.replaceRange(replacement, range.from, range.to);

  const startOffset = editor.posToOffset(range.from);
  editor.setSelection(range.from, editor.offsetToPos(startOffset + replacement.length));
}

module.exports = annotateText;
module.exports.directiveContext = directiveContext;
module.exports.directiveInsertion = directiveInsertion;
