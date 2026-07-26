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
    title: `Open ${label} in reading view in the main window`
  });

  link.addEventListener("click", async (event) => {
    event.preventDefault();
    await openInMain(path);
  });
}

function linkSection(title, items) {
  if (title) dv.header(2, title);

  for (const [label, path] of items) {
    if (app.vault.getAbstractFileByPath(path)) {
      mainWindowLink(label, path);
    } else {
      dv.paragraph(`*${label} not found.*`);
    }
  }
}

linkSection("", [
  ["Table of Contents", "Table of Contents.md"],
  ["Contents", "_control/bases/Contents.base"],
  ["Materials", "_control/bases/Materials.base"],
  ["Instructions", "_control/bases/Instructions.base"],
  ["Link Status", "_control/queries/Link Status.md"]
]);

linkSection("Workflow", [
  ["Stage Files", "_control/panels/Stage Files.md"],
  ["Commit Files", "_control/panels/Commit Files.md"],
  ["Define Plan", "_control/panels/Define Plan.md"],
  ["Dispatch Run", "_control/panels/Dispatch Run.md"],
  ["Write Responses", "_control/panels/Write Responses.md"],
  ["System Status", "_control/panels/System Status.md"],
  ["File State", "_control/panels/File State.md"]
]);

linkSection("Views", [
  ["Compiled Notes", "_control/queries/Compiled Notes.md"],
  ["Content Callouts", "_control/queries/Content Callouts.md"],
  ["Editorial Flags", "_control/queries/Editorial Flags.md"]
]);
```
