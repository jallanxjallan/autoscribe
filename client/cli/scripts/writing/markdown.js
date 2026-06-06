const { splitMarkdownFrontmatter } = require("../../lib/markdown");

function fail(script, message) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(1);
}

function stripLeadingResultFrontmatter(markdown) {
  const normalized = String(markdown || "").replace(/\r\n/g, "\n");
  const split = splitMarkdownFrontmatter(normalized);
  return split.hasFrontmatter ? split.body : normalized;
}

function ensureFinalNewline(text) {
  const source = String(text || "").replace(/\r\n/g, "\n");
  return source.endsWith("\n") ? source : `${source}\n`;
}

function composeMarkdownFromExistingFrontmatter({
  targetMarkdown,
  resultContent,
  relPath,
  script,
}) {
  const normalizedTarget = String(targetMarkdown || "").replace(/\r\n/g, "\n");
  const split = splitMarkdownFrontmatter(normalizedTarget);

  if (!split.hasFrontmatter) {
    fail(script, `${relPath}: target file has no frontmatter to preserve`);
  }

  const body = stripLeadingResultFrontmatter(resultContent).replace(/^\n+/, "");

  if (!body.trim()) {
    fail(script, `${relPath}: exported result content is empty after frontmatter stripping`);
  }

  return `---\n${split.frontmatter}\n---\n${ensureFinalNewline(body)}`;
}

module.exports = {
  stripLeadingResultFrontmatter,
  ensureFinalNewline,
  composeMarkdownFromExistingFrontmatter,
};
