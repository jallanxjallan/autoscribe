function createInternalLink(parent, app, path, text, beforeOpen) {
  const link = parent.createEl("a", { text });

  link.classList.add("internal-link");
  link.setAttribute("href", path);
  link.setAttribute("data-href", path);

  link.addEventListener("click", async (evt) => {
    evt.preventDefault();

    if (beforeOpen) {
      await beforeOpen();
    }

    app.workspace.openLinkText(path, "", false);
  });

  return link;
}

module.exports = {
  createInternalLink
};