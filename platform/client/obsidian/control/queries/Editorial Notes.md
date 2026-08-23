# Editorial Notes

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPath = app.workspace.getActiveFile()?.path || "";
const controlRoot = pathMod.posix.dirname(pathMod.posix.dirname(queryPath));
if (!queryPath || !controlRoot || controlRoot === ".") {
  throw new Error(`Could not infer Control root from query path: ${queryPath}`);
}
const loaderPath = pathMod.join(
  vaultBasePath,
  ...controlRoot.split("/").filter(Boolean),
  "scripts",
  "lib",
  "control-loader.js"
);
try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
const { createControlLoader } = nodeRequire(loaderPath);
const loader = createControlLoader({ app, queryPath, controlRoot });
const loadControl = (relativePath) => loader.requireControl(relativePath);
const { createInternalLink } = loadControl("scripts/lib/internal-link.js");
const { loadConfig } = loadControl("scripts/lib/config-loader.js");
const recordsConfig = loadConfig("records");
const queryConfig = loadConfig("queries").editorial_notes || {};
const uiConfig = loadConfig("ui");
const FOLDER = String(recordsConfig.editorial_note?.folder || "Editorial Notes");

const toolbar = dv.container.createDiv();
toolbar.style.marginBottom = "1rem";
const createButton = toolbar.createEl("button", { text: String(queryConfig.create_label || "New Editorial Note"), cls: "mod-cta" });
createButton.onclick = async () => {
  createButton.disabled = true;
  try {
    const createEditorialNote = loadControl("macros/create-editorial-note.js");
    await createEditorialNote({ app });
  } catch (error) {
    console.error("Create Editorial Note failed:", error);
    new Notice(`Create Editorial Note failed: ${error?.message || error}`, 10000);
  } finally {
    createButton.disabled = false;
  }
};

const folder = app.vault.getAbstractFileByPath(FOLDER);
const files = folder?.children
  ? folder.children
      .filter((file) => file.extension === "md")
      .sort((a, b) => a.basename.localeCompare(b.basename, undefined, { numeric: true, sensitivity: "base" }))
  : [];

if (!files.length) {
  dv.paragraph(folder ? "*No editorial notes found.*" : `*Folder not found: ${FOLDER}. It will be created with the first note.*`);
} else {
  const table = dv.container.createEl("table");
  const head = table.createEl("thead").createEl("tr");
  for (const label of Object.values(queryConfig.columns || {})) head.createEl("th", { text: String(label) });
  const body = table.createEl("tbody");

  for (const file of files) {
    const frontmatter = app.metadataCache.getFileCache(file)?.frontmatter ?? {};
    const row = body.createEl("tr");
    const noteCell = row.createEl("td");
    createInternalLink(noteCell, app, file.path, file.basename);
    row.createEl("td", { text: String(frontmatter[String(queryConfig.action_property || "action")] || String(uiConfig.missing_value || "—")) });

    const targetCell = row.createEl("td");
    const targets = Array.isArray(frontmatter[String(queryConfig.targets_property || "targets")])
      ? frontmatter[String(queryConfig.targets_property || "targets")]
      : frontmatter[String(queryConfig.targets_property || "targets")] ? [frontmatter[String(queryConfig.targets_property || "targets")]] : [];

    if (!targets.length) {
      targetCell.setText(String(uiConfig.missing_value || "—"));
    } else {
      targets.forEach((target, index) => {
        const raw = String(target?.path || target || "").replace(/^\[\[|\]\]$/g, "");
        if (index) targetCell.createSpan({ text: ", " });
        createInternalLink(targetCell, app, raw, raw.split("/").pop());
      });
    }

    row.createEl("td", { text: String(frontmatter[String(queryConfig.status_property || "status")] || String(uiConfig.missing_value || "—")) });
  }
}
````
