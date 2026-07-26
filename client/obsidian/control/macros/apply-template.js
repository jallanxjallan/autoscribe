"use strict";

function nodeRequire(name) {
  if (typeof require === "function") return require(name);
  if (typeof window !== "undefined" && window.require) return window.require(name);
  throw new Error(`Node module unavailable: ${name}`);
}

function fallbackNotify(message) {
  console.log(String(message));
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;
  if (typeof adapter?.getBasePath === "function") return adapter.getBasePath();
  if (adapter?.basePath) return adapter.basePath;
  throw new Error("Could not determine vault base path.");
}

function requireFromVault(app, vaultRelativePath) {
  const path = nodeRequire("path");
  const fullPath = path.join(getVaultBasePath(app), vaultRelativePath);
  const resolvedPath = nodeRequire.resolve(fullPath);
  delete nodeRequire.cache[resolvedPath];
  return nodeRequire(resolvedPath);
}

function isControlPath(path) {
  return String(path || "").startsWith("_control/");
}

function templateLabel(path) {
  return String(path)
    .replace(/^_control\/templates\//, "")
    .replace(/\.md$/i, "");
}

function recentNonControlFile(app) {
  const recentPaths = app.workspace.getLastOpenFiles?.() || [];
  for (const path of recentPaths) {
    if (isControlPath(path)) continue;
    const file = app.vault.getAbstractFileByPath(path);
    if (file?.extension === "md") return file;
  }
  return null;
}

async function resolveTargetFile(app, quickAddApi) {
  const active = app.workspace.getActiveFile();
  if (active && active.extension === "md" && !isControlPath(active.path)) {
    return active;
  }

  const recent = recentNonControlFile(app);
  if (recent) return recent;

  const candidates = app.vault
    .getMarkdownFiles()
    .filter((file) => !isControlPath(file.path))
    .sort((a, b) => a.path.localeCompare(b.path));

  if (candidates.length === 0) return null;

  return quickAddApi.suggester(
    candidates.map((file) => file.path),
    candidates,
    false,
    "Choose file to template"
  );
}

module.exports = async function applyTemplateMacro(params = {}) {
  const app = params.app || globalThis.app;
  const quickAddApi = params.quickAddApi;
  const { notify = fallbackNotify } = requireFromVault(
    app,
    "_control/scripts/lib/notify.js"
  );

  if (!app) throw new Error("Obsidian app object unavailable.");
  if (!quickAddApi?.suggester) {
    throw new Error("Apply Template must be run as a QuickAdd user script.");
  }

  const targetFile = await resolveTargetFile(app, quickAddApi);
  if (!targetFile) {
    notify("No non-control Markdown file is available to template.");
    return;
  }

  const templateFiles = app.vault
    .getMarkdownFiles()
    .filter((file) => file.path.startsWith("_control/templates/"))
    .sort((a, b) => a.path.localeCompare(b.path));

  if (templateFiles.length === 0) {
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

  const { applyTemplateToFile } = requireFromVault(
    app,
    "_control/scripts/templates/apply-template-tools.js"
  );

  const activeEditor = app.workspace.activeEditor?.editor || null;
  const editor = app.workspace.getActiveFile()?.path === targetFile.path
    ? activeEditor
    : null;

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
};
