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

module.exports = {
  forceCurrentLeafPresentation
};