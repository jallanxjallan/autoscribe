"use strict";

const { formatDirective } = require("../scripts/lib/directive.js");

function frontmatterEndLine(editor) {
  if (editor.getLine(0).trim() !== "---") return -1;

  for (let line = 1; line < editor.lineCount(); line += 1) {
    if (editor.getLine(line).trim() === "---") return line;
  }

  return -1;
}

function directiveInsertion(editor) {
  const endLine = frontmatterEndLine(editor);

  if (endLine < 0) {
    const point = { line: 0, ch: 0 };
    return {
      range: { from: point, to: point },
      prefix: "",
      suffix: "\n\n",
    };
  }

  const nextLine = endLine + 1;
  if (nextLine < editor.lineCount()) {
    const point = { line: nextLine, ch: 0 };
    return {
      range: { from: point, to: point },
      prefix: "",
      suffix: "\n\n",
    };
  }

  const point = {
    line: endLine,
    ch: editor.getLine(endLine).length,
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

async function insertDirective({ app, directivePrompt = promptDirective }) {
  const editor = app.workspace.activeEditor?.editor;
  if (!editor) {
    throw new Error("Open a Markdown note in edit mode before inserting a directive.");
  }

  const instruction = await directivePrompt();
  if (!instruction?.trim()) return;

  const insertion = directiveInsertion(editor);
  const replacement = `${insertion.prefix}${formatDirective(instruction)}${insertion.suffix}`;

  editor.replaceRange(replacement, insertion.range.from, insertion.range.to);

  const startOffset = editor.posToOffset(insertion.range.from);
  editor.setSelection(
    insertion.range.from,
    editor.offsetToPos(startOffset + replacement.length)
  );
}

module.exports = insertDirective;
module.exports.directiveInsertion = directiveInsertion;
