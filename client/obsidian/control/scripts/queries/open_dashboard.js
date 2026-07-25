// Open _control/Dashboard.md in the left sidebar.

module.exports = async ({ app }) => {
  const candidates = [
    "_control/Dashboard.md",
    "Dashboard.md",
  ];

  const file = candidates
    .map((path) => app.vault.getAbstractFileByPath(path))
    .find((candidate) => candidate?.extension === "md");

  if (!file) {
    console.warn("Dashboard not found.");
    return;
  }

  const existingLeaf = app.workspace
    .getLeavesOfType("markdown")
    .find((leaf) => leaf.view?.file?.path === file.path);

  if (existingLeaf) {
    await app.workspace.revealLeaf(existingLeaf);
    return;
  }

  const leaf = app.workspace.getLeftLeaf(false);
  await leaf.openFile(file, { active: true });
  await app.workspace.revealLeaf(leaf);
};
