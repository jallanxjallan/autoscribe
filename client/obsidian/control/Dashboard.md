# Dashboard

```dataviewjs
async function openInMain(path) {
  const file = app.vault.getAbstractFileByPath(path);
  if (!file) return;

  const leaf = app.workspace.getLeaf("tab");
  await leaf.openFile(file);
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

const tocPath = "Table of Contents.md";
const toc = app.vault.getAbstractFileByPath(tocPath);

if (toc?.extension === "md") {
  mainWindowLink("Table of Contents", tocPath);
} else {
  dv.paragraph("*No Table of Contents in this vault.*");
}

const contentsPath = "_control/bases/Contents.base";
const contents = app.vault.getAbstractFileByPath(contentsPath);

if (contents) {
  mainWindowLink("Contents", contentsPath);
} else {
  dv.paragraph("*Contents base not found.*");
}
```

## Workflow

- [[_control/panels/Stage Files|Stage Files]]
- [[_control/panels/Commit Files|Commit Files]]
- [[_control/panels/Define Plan|Define Plan]]
- [[_control/panels/Dispatch Run|Dispatch Run]]
- [[_control/panels/Write Responses|Write Responses]]
- [[_control/panels/File State|File State]]

## Views

- [[_control/queries/Compiled Notes|Compiled Notes]]
- [[_control/queries/Content Callouts|Content Callouts]]
- [[_control/queries/Editorial Flags|Editorial Flags]]

## Reference

- [[_control/queries/Materials Index|Materials Index]]
- [[_control/queries/Instructions Index|Instructions Index]]
- [[_control/queries/Tag Index|Tag Index]]
