// _control/scripts/open-dashboard.js

module.exports = async ({ app }) => {
  const candidates = [
    "_control/Dashboard.md",
    "Dashboard.md",
    "_control/queries/Dashboard.md",
  ];

  const file = candidates
    .map(path => app.vault.getAbstractFileByPath(path))
    .find(file => file && file.extension === "md");

  if (!file) {
    console.warn("Vault Dashboard not found.");
    return;
  }

  const existingLeaf = app.workspace
    .getLeavesOfType("markdown")
    .find(leaf => leaf.view?.file?.path === file.path);

  if (existingLeaf) {
    app.workspace.setActiveLeaf(existingLeaf, { focus: true });
    return;
  }

  const leaf = app.workspace.getLeaf(false);
  await leaf.openFile(file, { active: true });
};
