"use strict";

const { extractWikiLinks, resolveWikilink } = require("./wikilinks");

function splitFrontmatter(text) {
  const source = String(text || "");
  if (!source.startsWith("---\n") && !source.startsWith("---\r\n")) {
    return { frontmatter: "", body: source, hasFrontmatter: false };
  }
  const match = source.match(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/);
  if (!match) return { frontmatter: "", body: source, hasFrontmatter: false };
  return {
    frontmatter: match[0],
    body: source.slice(match[0].length),
    hasFrontmatter: true,
  };
}

function wikiDisplayText(rawBody) {
  const body = String(rawBody || "").trim();
  const pipe = body.indexOf("|");
  if (pipe >= 0) return body.slice(pipe + 1).trim();
  const target = body.replace(/^!/, "").trim();
  const hash = target.indexOf("#");
  const withoutSubpath = hash >= 0 ? target.slice(0, hash) : target;
  const leaf = withoutSubpath.split("/").pop() || withoutSubpath;
  return leaf.replace(/\.md$/i, "").trim();
}

function parseWikiBody(raw) {
  const transclusion = String(raw || "").startsWith("![[");
  const inner = String(raw || "").replace(/^!?\[\[/, "").replace(/\]\]$/, "");
  const pipe = inner.indexOf("|");
  const targetWithSubpath = (pipe >= 0 ? inner.slice(0, pipe) : inner).trim();
  const hash = targetWithSubpath.indexOf("#");
  return {
    transclusion,
    inner,
    display: wikiDisplayText(inner),
    targetWithSubpath,
    linkpath: (hash >= 0 ? targetWithSubpath.slice(0, hash) : targetWithSubpath).trim(),
    subpath: hash >= 0 ? targetWithSubpath.slice(hash) : "",
  };
}

function cleanHeadingText(line) {
  return String(line || "").replace(/^\s{0,3}#{1,6}\s+/, "").replace(/\s+#+\s*$/, "").trim();
}

function extractHeadingSection(text, heading) {
  const wanted = String(heading || "").replace(/^#/, "").trim().toLowerCase();
  if (!wanted) return String(text || "");
  const lines = String(text || "").split(/\r?\n/);
  let start = -1;
  let level = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const m = lines[i].match(/^\s{0,3}(#{1,6})\s+(.+?)\s*$/);
    if (!m) continue;
    if (cleanHeadingText(lines[i]).toLowerCase() === wanted) {
      start = i + 1;
      level = m[1].length;
      break;
    }
  }
  if (start < 0) throw new Error(`Transclusion heading was not found: #${heading}`);
  let end = lines.length;
  for (let i = start; i < lines.length; i += 1) {
    const m = lines[i].match(/^\s{0,3}(#{1,6})\s+/);
    if (m && m[1].length <= level) { end = i; break; }
  }
  return lines.slice(start, end).join("\n").trim();
}

function extractBlock(text, blockId) {
  const id = String(blockId || "").replace(/^\^/, "").trim();
  if (!id) return String(text || "");
  const lines = String(text || "").split(/\r?\n/);
  const marker = new RegExp(`(?:^|\\s)\\^${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`);
  for (let i = 0; i < lines.length; i += 1) {
    if (!marker.test(lines[i])) continue;
    const cleaned = lines[i].replace(marker, "").trimEnd();
    if (cleaned.trim()) return cleaned.trim();
    let start = i - 1;
    while (start >= 0 && lines[start].trim()) start -= 1;
    return lines.slice(start + 1, i).join("\n").trim();
  }
  throw new Error(`Transclusion block was not found: ^${id}`);
}

function selectTranscludedText(fileText, subpath) {
  const { body } = splitFrontmatter(fileText);
  if (!subpath) return body.trim();
  if (subpath.startsWith("#^")) return extractBlock(body, subpath.slice(2));
  if (subpath.startsWith("#")) return extractHeadingSection(body, subpath.slice(1));
  return body.trim();
}

function externalLinkMatches(text) {
  const source = String(text || "");
  const matches = [];
  const occupied = [];
  const add = (start, end, raw, replacement) => {
    if (occupied.some(([a, b]) => start < b && end > a)) return;
    occupied.push([start, end]);
    matches.push({ start, end, raw, replacement });
  };

  // Markdown links and images. Images keep alt text in the processing body.
  const markdown = /!?\[([^\]]*)\]\(([^)]+)\)/g;
  let m;
  while ((m = markdown.exec(source)) !== null) add(m.index, m.index + m[0].length, m[0], m[1]);

  // Angle-bracket URL autolinks.
  const angle = /<https?:\/\/[^>\s]+>/gi;
  while ((m = angle.exec(source)) !== null) add(m.index, m.index + m[0].length, m[0], m[0].slice(1, -1));

  // Bare HTTP(S) URLs; leave them visible as plain text after flattening.
  const bare = /https?:\/\/[^\s<>\])}]+[^\s<>\])}.,;:!?]/gi;
  while ((m = bare.exec(source)) !== null) add(m.index, m.index + m[0].length, m[0], m[0]);

  return matches.sort((a, b) => a.start - b.start);
}

function applyReplacements(text, replacements) {
  let out = String(text || "");
  for (const item of [...replacements].sort((a, b) => b.start - a.start)) {
    out = out.slice(0, item.start) + item.replacement + out.slice(item.end);
  }
  return out;
}

async function expandTransclusions(app, body, sourcePath, state) {
  const source = String(body || "");
  const links = extractWikiLinks(source);
  const replacements = [];

  for (const link of links) {
    state.links.push(link.raw);
    const parsed = parseWikiBody(link.raw);
    if (!parsed.transclusion) {
      replacements.push({ start: link.index, end: link.index + link.raw.length, replacement: parsed.display });
      continue;
    }

    let resolved;
    if (!parsed.linkpath) {
      const sameFile = app.vault.getAbstractFileByPath(sourcePath);
      resolved = { file: sameFile, path: sameFile?.path ?? null, vaultPath: sameFile?.path ?? null };
    } else {
      resolved = resolveWikilink(app, { ...link, target: parsed.linkpath }, sourcePath);
    }
    if (!resolved.file) throw new Error(`Could not resolve transclusion ${link.raw} from ${sourcePath}`);
    const key = `${resolved.file.path}${parsed.subpath}`;
    if (state.stack.has(key)) throw new Error(`Recursive transclusion detected at ${link.raw} from ${sourcePath}`);

    state.stack.add(key);
    const targetText = await app.vault.cachedRead(resolved.file);
    const selected = selectTranscludedText(targetText, parsed.subpath);
    const expanded = await expandTransclusions(app, selected, resolved.file.path, state);
    state.stack.delete(key);
    replacements.push({ start: link.index, end: link.index + link.raw.length, replacement: expanded });
  }

  return applyReplacements(source, replacements);
}

async function prepareDispatchDocument(app, file) {
  if (!file || file.extension !== "md") throw new Error("Dispatch preparation requires a Markdown file.");
  const original = await app.vault.cachedRead(file);
  const split = splitFrontmatter(original);
  const state = { links: [], stack: new Set([file.path]) };
  let body = await expandTransclusions(app, split.body, file.path, state);

  const external = externalLinkMatches(body);
  state.links.push(...external.map((item) => item.raw));
  body = applyReplacements(body, external);

  const links = [...new Set(state.links.map((value) => String(value).trim()).filter(Boolean))];
  const rebuilt = `${split.frontmatter}${body}`;
  if (rebuilt !== original) await app.vault.modify(file, rebuilt);
  await app.fileManager.processFrontMatter(file, (frontmatter) => {
    frontmatter.links = links;
  });
  return { file, links, changed: rebuilt !== original };
}

module.exports = {
  splitFrontmatter,
  wikiDisplayText,
  parseWikiBody,
  extractHeadingSection,
  extractBlock,
  selectTranscludedText,
  externalLinkMatches,
  applyReplacements,
  expandTransclusions,
  prepareDispatchDocument,
};
