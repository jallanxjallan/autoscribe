async function forceCurrentLeafPresentation(app) {
  const activeFile = app.workspace.getActiveFile();

  if (!activeFile) return;

  const leaves = app.workspace.getLeavesOfType("markdown");

  for (const leaf of leaves) {
    const state = typeof leaf.getViewState === "function"
      ? leaf.getViewState()
      : null;

    if (state?.state?.file !== activeFile.path) continue;

    try {
      if (typeof leaf.setPinned === "function") {
        leaf.setPinned(true);
      } else if (typeof leaf.togglePinned === "function" && leaf.pinned === false) {
        leaf.togglePinned();
      }
    } catch (_) {}

    try {
      if (
        typeof leaf.setViewState === "function" &&
        state?.state?.mode !== "preview"
      ) {
        await leaf.setViewState(
          {
            ...state,
            state: {
              ...(state?.state ?? {}),
              file: activeFile.path,
              mode: "preview"
            }
          },
          { focus: false }
        );
      }
    } catch (_) {}
  }
}

async function openFileInMain(app, fileOrPath, { mode = "preview", reveal = true } = {}) {
  const file = typeof fileOrPath === "string"
    ? app.vault.getAbstractFileByPath(fileOrPath)
    : fileOrPath;
  if (!file) throw new Error(`File not found: ${fileOrPath}`);

  const existing = app.workspace.getLeavesOfType("markdown")
    .find((leaf) => leaf.view?.file?.path === file.path && leaf.getRoot?.() === app.workspace.rootSplit);
  const leaf = existing || app.workspace.getLeaf("tab");
  if (file.extension === "md") {
    await leaf.setViewState({
      type: "markdown",
      state: { file: file.path, mode, source: mode !== "preview" },
      active: true,
    });
  } else {
    await leaf.openFile(file, { active: true });
  }
  if (reveal) await app.workspace.revealLeaf(leaf);
  app.workspace.setActiveLeaf(leaf, { focus: true });
  return leaf;
}

module.exports = {
  forceCurrentLeafPresentation,
  openFileInMain,
};
