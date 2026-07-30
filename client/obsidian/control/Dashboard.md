x# Dashboard

```dataviewjs
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
      state: {
        file: file.path,
        mode: "preview",
        source: false,
      },
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

function mainWindowLink(label, path) {
  const row = dv.el("div", "", {
    attr: {
      style: "margin: 0.25em 0;"
    }
  });

  const link = row.createEl("a", {
    text: label,
    href: "#",
    title: `Open ${label} in the main window`
  });

  link.addEventListener("click", async (event) => {
    event.preventDefault();
    await openInMain(path);
  });
}

function normalizePath(path) {
  return path.replace(/^\/+|\/+$/g, "").toLowerCase();
}

function resolveFolderPath(requestedPath) {
  const exact = app.vault.getAbstractFileByPath(requestedPath);
  if (exact?.children) return exact.path;

  const wanted = normalizePath(requestedPath);
  const folder = app.vault.getAllLoadedFiles().find((item) =>
    item?.children && normalizePath(item.path) === wanted
  );

  return folder?.path ?? null;
}

function filesInFolder(folderPath) {
  return app.vault.getFiles()
    .filter((file) => file.parent?.path === folderPath)
    .sort((a, b) => a.basename.localeCompare(b.basename, undefined, {
      numeric: true,
      sensitivity: "base"
    }));
}

function folderSection(title, requestedPath) {
  dv.header(2, title);

  const folderPath = resolveFolderPath(requestedPath);
  if (!folderPath) {
    dv.paragraph(`*Folder not found: ${requestedPath}*`);
    return;
  }

  const files = filesInFolder(folderPath);
  if (files.length === 0) {
    dv.paragraph("*No files found.*");
    return;
  }

  for (const file of files) {
    mainWindowLink(file.basename, file.path);
  }
}


folderSection("Queries", "_control/queries");
folderSection("Workflow", "_control/panels");
folderSection("Views", "views");
```
