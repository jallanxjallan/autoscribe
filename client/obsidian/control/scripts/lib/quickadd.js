"use strict";

const { isControlPath, isMarkdownFile, markdownFiles } = require("./vault-files.js");

function templateLabel(path, templatesRoot = "_control/templates") {
  const escaped = String(templatesRoot).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return String(path || "")
    .replace(new RegExp(`^${escaped}/`), "")
    .replace(/\.md$/i, "");
}

function recentNonControlFile(app, controlRoot = "_control") {
  for (const path of app.workspace.getLastOpenFiles?.() || []) {
    if (isControlPath(path, controlRoot)) continue;
    const file = app.vault.getAbstractFileByPath(path);
    if (isMarkdownFile(file)) return file;
  }
  return null;
}

async function resolveTargetMarkdownFile({ app, quickAddApi, controlRoot = "_control", prompt = "Choose file" }) {
  const active = app.workspace.getActiveFile();
  if (isMarkdownFile(active) && !isControlPath(active.path, controlRoot)) return active;

  const recent = recentNonControlFile(app, controlRoot);
  if (recent) return recent;

  const candidates = markdownFiles(app, { excludeControl: true, controlRoot })
    .sort((a, b) => a.path.localeCompare(b.path));
  if (!candidates.length) return null;

  return quickAddApi.suggester(
    candidates.map((file) => file.path),
    candidates,
    false,
    prompt
  );
}

module.exports = { templateLabel, recentNonControlFile, resolveTargetMarkdownFile };
