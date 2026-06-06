function normalizeMarkdownText(markdown) {
  return String(markdown || "").replace(/\r\n/g, "\n");
}

function splitMarkdownFrontmatter(markdown) {
  const source = normalizeMarkdownText(markdown);

  if (!source.startsWith("---\n")) {
    return { frontmatter: "", body: source, hasFrontmatter: false };
  }

  const end = source.indexOf("\n---\n", 4);

  if (end === -1) {
    return { frontmatter: "", body: source, hasFrontmatter: false };
  }

  return {
    frontmatter: source.slice(4, end),
    body: source.slice(end + 5),
    hasFrontmatter: true,
  };
}

function stripFrontmatter(markdown) {
  const split = splitMarkdownFrontmatter(markdown);
  return split.hasFrontmatter ? split.body : normalizeMarkdownText(markdown);
}

function parseFrontmatterScalar(rawValue) {
  const text = String(rawValue ?? "").trim();

  if (text === "") return {};
  if (text === "{}") return {};
  if (text === "[]") return [];
  if (text === "null" || text === "~") return null;
  if (text === "true") return true;
  if (text === "false") return false;

  if (
    (text.startsWith('"') && text.endsWith('"')) ||
    (text.startsWith("'") && text.endsWith("'"))
  ) {
    return text.slice(1, -1);
  }

  if (text.startsWith("[") && text.endsWith("]")) {
    const inner = text.slice(1, -1).trim();
    if (!inner) return [];
    return inner
      .split(",")
      .map(item => String(item).trim())
      .filter(Boolean)
      .map(item => parseFrontmatterScalar(item));
  }

  return text;
}

function parseSimpleFrontmatterText(frontmatter) {
  const root = {};
  const stack = [{ indent: -1, object: root }];

  for (const rawLine of String(frontmatter || "").replace(/\r\n/g, "\n").split("\n")) {
    if (!rawLine.trim() || rawLine.trim().startsWith("#")) continue;

    const match = rawLine.match(/^(\s*)([A-Za-z0-9_-]+):(?:\s*(.*?))?\s*$/);
    if (!match) continue;

    const indent = match[1].replace(/\t/g, "  ").length;
    const key = match[2];
    const rawValue = match[3] ?? "";

    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].object;
    const value = parseFrontmatterScalar(rawValue);
    parent[key] = value;

    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      rawValue.trim() === ""
    ) {
      stack.push({ indent, object: value });
    }
  }

  return root;
}

function parseFrontmatterDataFromMarkdown(markdown) {
  const { frontmatter } = splitMarkdownFrontmatter(markdown);
  return parseSimpleFrontmatterText(frontmatter);
}

function getFrontmatterTextFromMarkdown(markdown, key) {
  const data = parseFrontmatterDataFromMarkdown(markdown);
  const entry = Object.entries(data).find(
    ([k]) => String(k).toLowerCase() === String(key).toLowerCase()
  );

  return entry ? String(entry[1] || "").trim() : "";
}

function dequoteBlockquoteLine(line) {
  return String(line || "").replace(/^>\s?/, "");
}

function collectBlockquoteBlocks(markdown) {
  const body = stripFrontmatter(markdown);
  const lines = body.split(/\r?\n/);
  const blocks = [];
  let current = [];

  function flush() {
    const content = current.join("\n").trim();
    if (content) blocks.push(content);
    current = [];
  }

  for (const line of lines) {
    if (/^>\s?/.test(line)) {
      current.push(dequoteBlockquoteLine(line));
      continue;
    }

    if (/^\s*$/.test(line)) {
      flush();
      continue;
    }

    flush();
  }

  flush();
  return blocks;
}

function ensureFinalNewline(text) {
  const source = normalizeMarkdownText(text);
  return source.endsWith("\n") ? source : `${source}\n`;
}

module.exports = {
  normalizeMarkdownText,
  splitMarkdownFrontmatter,
  stripFrontmatter,
  parseFrontmatterScalar,
  parseSimpleFrontmatterText,
  parseFrontmatterDataFromMarkdown,
  getFrontmatterTextFromMarkdown,
  dequoteBlockquoteLine,
  collectBlockquoteBlocks,
  ensureFinalNewline,
};
