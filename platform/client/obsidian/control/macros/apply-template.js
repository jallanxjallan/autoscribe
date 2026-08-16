"use strict";


async function applyTemplate(params = {}) {
  const app = params.app || globalThis.app;
  const quickAddApi = params.quickAddApi;

  if (!app) throw new Error("Obsidian app object unavailable.");

  const nodeRequire = require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  if (!base) throw new Error("Could not determine vault base path.");

  const load = (relativePath) => nodeRequire(
    path.join(base, "_control", "scripts", ...relativePath.split("/"))
  );
  const { notify } = load("lib/notify.js");
  const { markdownFiles } = load("lib/vault-files.js");
  const { templateLabel, resolveTargetMarkdownFile } = load("lib/quickadd.js");
  const { applyTemplateToFile } = load("templates/apply-template-tools.js");

  if (!quickAddApi?.suggester) {
    throw new Error("Apply Template must be run as a QuickAdd user script.");
  }

  const targetFile = await resolveTargetMarkdownFile({
    app,
    quickAddApi,
    prompt: "Choose file to template",
  });
  if (!targetFile) {
    notify("No non-control Markdown file is available to template.");
    return;
  }

  const templateFiles = markdownFiles(app)
    .filter((file) => file.path.startsWith("_control/templates/"))
    .sort((a, b) => a.path.localeCompare(b.path));
  if (!templateFiles.length) {
    notify("No templates found under _control/templates.");
    return;
  }

  const chosen = await quickAddApi.suggester(
    templateFiles.map((file) => templateLabel(file.path)),
    templateFiles,
    false,
    `Insert template into ${targetFile.path}`
  );
  if (!chosen) return;

  notify(`Applying ${templateLabel(chosen.path)}…`);

  const activeEditor = app.workspace.activeEditor?.editor || null;
  const editor = app.workspace.getActiveFile()?.path === targetFile.path ? activeEditor : null;

  try {
    const result = await applyTemplateToFile({
      app,
      targetPath: targetFile.path,
      templatePath: chosen.path,
      editor,
    });
    notify(`Inserted ${templateLabel(chosen.path)} → ${result.path}`);
    console.log("Apply Template complete:", result);
  } catch (error) {
    console.error("Apply Template failed:", error);
    notify(`Apply Template failed: ${error?.message || String(error)}`, 9000);
  }
}

module.exports = applyTemplate;
