"use strict";

const { getVaultAbsolutePath } = require("./vault-paths");

function normalizeRelPath(relPath) {
  return String(relPath || "")
    .replace(/\\/g, "/")
    .replace(/^\.\//, "")
    .replace(/^\/+/, "")
    .replace(/\/+/g, "/")
    .trim();
}

function normalizeWikiTarget(target) {
  return String(target || "")
    .split("|")[0]
    .split("#")[0]
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.\//, "")
    .replace(/^\//, "")
    .replace(/\.md$/i, "");
}

function markdownStem(relPath) {
  const filename = normalizeRelPath(relPath).split("/").pop() || "";
  return filename.replace(/\.md$/i, "");
}

function withoutMarkdownExtension(relPath) {
  return normalizeRelPath(relPath).replace(/\.md$/i, "");
}

function wikiAliasesForPath(relPath) {
  const normalized = normalizeRelPath(relPath);
  const noExt = withoutMarkdownExtension(normalized);
  const filename = normalized.split("/").pop() || "";
  const stem = markdownStem(normalized);
  return [noExt, normalized, stem, filename].filter(Boolean);
}

function wikiAliasesForRecord(record) {
  return wikiAliasesForPath(record.path);
}

function extractWikiLinks(text) {
  const links = [];
  const re = /!?\[\[([^\]]+?)\]\]/g;
  let match;

  while ((match = re.exec(String(text || ""))) !== null) {
    const raw = match[0];
    const body = match[1];
    const target = normalizeWikiTarget(body);
    const aliasParts = body.split("|").slice(1);
    const alias = aliasParts.length ? aliasParts.join("|").trim() : null;
    links.push({ raw, target, alias, index: match.index });
  }

  return links;
}

function parseWikilinks(text) {
  return extractWikiLinks(text);
}

function removeWikiLinks(text) {
  return String(text || "").replace(/!?\[\[[^\]]+?\]\]/g, "").trim();
}

function stripMarkdownLinks(text) {
  return String(text || "")
    .replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?\]\]/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();
}

function resolveWikilink(app, link, sourcePath) {
  const dest = app?.metadataCache?.getFirstLinkpathDest?.(link.target, sourcePath) ?? null;

  return {
    ...link,
    resolved: Boolean(dest),
    file: dest,
    vaultPath: dest?.path ?? null,
    path: dest?.path ?? null,
    absolutePath: dest?.path ? getVaultAbsolutePath(app, dest.path) : null,
    basename: dest?.basename ?? null,
  };
}

function extractResolvedWikilinks({ app, text, sourcePath }) {
  return parseWikilinks(text).map((link) => resolveWikilink(app, link, sourcePath));
}

function flattenInstructionLinks(tree) {
  const out = [];
  function walk(nodes) {
    for (const node of nodes ?? []) {
      for (const link of node.links ?? []) out.push(link);
      walk(node.children ?? []);
    }
  }
  walk(tree);
  return out;
}

module.exports = {
  normalizeRelPath,
  normalizeWikiTarget,
  markdownStem,
  withoutMarkdownExtension,
  wikiAliasesForPath,
  wikiAliasesForRecord,
  extractWikiLinks,
  parseWikilinks,
  removeWikiLinks,
  stripMarkdownLinks,
  resolveWikilink,
  extractResolvedWikilinks,
  flattenInstructionLinks,
};
