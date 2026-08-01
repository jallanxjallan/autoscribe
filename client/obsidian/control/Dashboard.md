# Dashboard

```dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(vaultRoot, "_control", ...relativePath.split("/")));

async function openInMain(path) {
  const file = app.vault.getAbstractFileByPath(path);
  if (!file) {
    new Notice(`File not found: ${path}`);
    return;
  }
  const leaf = app.workspace.getLeaf("tab");
  if (file.extension === "md") {
    await leaf.setViewState({
      type: "markdown",
      state: { file: file.path, mode: "preview", source: false },
      active: true,
      pinned: true,
    });
  } else {
    await leaf.openFile(file);
    const state = leaf.getViewState();
    state.pinned = true;
    await leaf.setViewState(state);
  }
  app.workspace.setActiveLeaf(leaf, { focus: true });
}

function link(label, path) {
  const row = dv.el("div", "", { attr: { style: "margin:.25em 0;" } });
  const anchor = row.createEl("a", { text: label, href: "#" });
  anchor.onclick = async (event) => {
    event.preventDefault();
    await openInMain(path);
  };
}

function command(label, macroPath) {
  const row = dv.el("div", "", { attr: { style: "margin:.35em 0;" } });
  const button = row.createEl("button", { text: label });
  button.style.minWidth = "14rem";
  button.onclick = async () => {
    button.disabled = true;
    try {
      const run = loadControl(macroPath);
      await run({ app });
    } catch (error) {
      console.error(`${label} failed:`, error);
      new Notice(`${label} failed: ${error?.message || error}`, 10000);
    } finally {
      button.disabled = false;
    }
  };
}

function normalizePath(path) {
  return path.replace(/^\/+|\/+$/g, "").toLowerCase();
}

function resolveFolderPath(requestedPath) {
  const exact = app.vault.getAbstractFileByPath(requestedPath);
  if (exact?.children) return exact.path;
  const wanted = normalizePath(requestedPath);
  return app.vault.getAllLoadedFiles().find((item) => item?.children && normalizePath(item.path) === wanted)?.path ?? null;
}

function filesInFolder(folderPath) {
  return app.vault.getFiles()
    .filter((file) => file.parent?.path === folderPath)
    .sort((a, b) => a.basename.localeCompare(b.basename, undefined, { numeric: true, sensitivity: "base" }));
}

function folderSection(title, requestedPath) {
  dv.header(2, title);
  const folderPath = resolveFolderPath(requestedPath);
  if (!folderPath) {
    dv.paragraph(`*Folder not found: ${requestedPath}*`);
    return;
  }
  const files = filesInFolder(folderPath);
  if (!files.length) {
    dv.paragraph("*No files found.*");
    return;
  }
  for (const file of files) link(file.basename, file.path);
}

dv.header(2, "Workflow");
for (const [label, macro] of [
  ["Commit Files", "macros/autoscribe-commit-files.js"],
  ["Stage Files", "macros/autoscribe-stage-files.js"],
  ["Define Plan", "macros/autoscribe-define-plan.js"],
  ["Dispatch Run", "macros/autoscribe-dispatch-run.js"],
  ["Write Responses", "macros/autoscribe-write-responses.js"],
  ["File State", "macros/autoscribe-file-state.js"],
]) command(label, macro);

link("System Status", "_control/panels/System Status.md");
folderSection("Queries", "_control/queries");
folderSection("Views", "views");
```
