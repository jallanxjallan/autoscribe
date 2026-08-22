module.exports = async (params) => {
  const { app } = params;

  const leaf = app.workspace.getMostRecentLeaf();
  const view = leaf?.view;
  const editor = view?.editor;

  if (!editor) {
    console.warn("Toggle Transclusions: no active Markdown editor.");
    return;
  }

  const text = editor.getValue();

  // Split off opening YAML frontmatter and leave it completely untouched.
  let frontmatter = "";
  let body = text;

  if (text.startsWith("---\n") || text.startsWith("---\r\n")) {
    const match = text.match(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/);

    if (match) {
      frontmatter = match[0];
      body = text.slice(frontmatter.length);
    }
  }

  // Toggle wikilinks only in the document body:
  // [[note]]  <->  ![[note]]
  const toggledBody = body.replace(
    /(!?)\[\[([^\]]+)\]\]/g,
    (_, bang, target) =>
      bang ? `[[${target}]]` : `![[${target}]]`
  );

  if (toggledBody === body) {
    console.info("Toggle Transclusions: no body wikilinks found.");
    return;
  }

  const cursor = editor.getCursor();

  editor.setValue(frontmatter + toggledBody);

  // Restore cursor where possible.
  try {
    editor.setCursor(cursor);
  } catch (_) {}

  console.info("Toggle Transclusions: complete.");
};
