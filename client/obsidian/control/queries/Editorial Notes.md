# Editorial Notes

````dataviewjs
const FOLDER = "Editorial Notes";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPath = app.workspace.getActiveFile()?.path || "";
const markerIndex = queryPath.indexOf("/queries/");

if (markerIndex === -1) {
  throw new Error(`Query is not inside a queries folder: ${queryPath}`);
}

const controlRoot = queryPath.slice(0, markerIndex);
const loadControl = (relativePath) => nodeRequire(
  pathMod.join(vaultBasePath, ...controlRoot.split("/").filter(Boolean), ...relativePath.split("/"))
);
const { createInternalLink } = loadControl("scripts/lib/internal-link.js");

const toolbar = dv.container.createDiv();
toolbar.style.marginBottom = "1rem";
const createButton = toolbar.createEl("button", { text: "New Editorial Note", cls: "mod-cta" });
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
  for (const label of ["Note", "Action", "Targets", "Status"]) head.createEl("th", { text: label });
  const body = table.createEl("tbody");

  for (const file of files) {
    const frontmatter = app.metadataCache.getFileCache(file)?.frontmatter ?? {};
    const row = body.createEl("tr");
    const noteCell = row.createEl("td");
    createInternalLink(noteCell, app, file.path, file.basename);
    row.createEl("td", { text: String(frontmatter.action || "—") });

    const targetCell = row.createEl("td");
    const targets = Array.isArray(frontmatter.targets)
      ? frontmatter.targets
      : frontmatter.targets ? [frontmatter.targets] : [];

    if (!targets.length) {
      targetCell.setText("—");
    } else {
      targets.forEach((target, index) => {
        const raw = String(target?.path || target || "").replace(/^\[\[|\]\]$/g, "");
        if (index) targetCell.createSpan({ text: ", " });
        createInternalLink(targetCell, app, raw, raw.split("/").pop());
      });
    }

    row.createEl("td", { text: String(frontmatter.status || "—") });
  }
}
````
