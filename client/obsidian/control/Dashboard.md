# Dashboard

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
        source: false
      },
      active: true
    });
  } else {
    await leaf.openFile(file);
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

function linkSection(title, items) {
  dv.header(2, title);

  for (const [label, path] of items) {
    if (app.vault.getAbstractFileByPath(path)) {
      mainWindowLink(label, path);
    } else {
      dv.paragraph(`*${label} not found.*`);
    }
  }
}

const tocPath = "Table of Contents.md";
if (app.vault.getAbstractFileByPath(tocPath)) {
  mainWindowLink("Table of Contents", tocPath);
} else {
  dv.paragraph("*No Table of Contents in this vault.*");
}

const contentsPath = "_control/bases/Contents.base";
if (app.vault.getAbstractFileByPath(contentsPath)) {
  mainWindowLink("Contents", contentsPath);
} else {
  dv.paragraph("*Contents base not found.*");
}

linkSection("Workflow", [
  ["Stage Files", "_control/panels/Stage Files.md"],
  ["Commit Files", "_control/panels/Commit Files.md"],
  ["Define Plan", "_control/panels/Define Plan.md"],
  ["Dispatch Run", "_control/panels/Dispatch Run.md"],
  ["Write Responses", "_control/panels/Write Responses.md"],
  ["File State", "_control/panels/File State.md"]
]);

linkSection("Views", [
  ["Compiled Notes", "_control/queries/Compiled Notes.md"],
  ["Content Callouts", "_control/queries/Content Callouts.md"],
  ["Editorial Flags", "_control/queries/Editorial Flags.md"]
]);

linkSection("Reference", [
  ["Materials Index", "_control/queries/Materials Index.md"],
  ["Instructions Index", "_control/queries/Instructions Index.md"],
  ["Tag Index", "_control/queries/Tag Index.md"]
]);
```
