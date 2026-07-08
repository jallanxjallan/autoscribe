const { splitMarkdownFrontmatter } = require("../../lib/markdown");
const { extractRecordContent } = require("./pending");

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

function setFrontmatterField(frontmatter, key, value) {
  const source = String(frontmatter || "").replace(/\r\n/g, "\n");
  const lineRe = new RegExp(`^${key}\\s*:\\s*.*$`, "m");
  const line = `${key}: ${value}`;

  if (lineRe.test(source)) {
    return source.replace(lineRe, line);
  }

  return source.trimEnd() ? `${source.trimEnd()}\n${line}` : line;
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

  const unwrappedContent = extractRecordContent(resultContent);
  const body = stripLeadingResultFrontmatter(unwrappedContent).replace(/^\n+/, "");

  if (!body.trim()) {
    fail(script, `${relPath}: exported result content is empty after frontmatter stripping`);
  }

  const frontmatter = setFrontmatterField(split.frontmatter, "status", "ai-generated");

  return `---\n${frontmatter}\n---\n${ensureFinalNewline(body)}`;
}

module.exports = {
  stripLeadingResultFrontmatter,
  ensureFinalNewline,
  setFrontmatterField,
  composeMarkdownFromExistingFrontmatter,
};
