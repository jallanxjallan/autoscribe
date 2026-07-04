"use strict";

function asText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  if (Array.isArray(value)) return value.map(v => String(v)).join(", ");

  const text = String(value).trim();
  return text || fallback;
}

function asList(value) {
  if (value === null || value === undefined) return [];

  const values = Array.isArray(value) ? value : [value];
  const seen = new Set();
  const result = [];

  for (const item of values.flatMap(item => String(item || "").split(","))) {
    const text = item.trim();
    if (!text) continue;

    const key = text.toLowerCase();
    if (seen.has(key)) continue;

    seen.add(key);
    result.push(text);
  }

  return result;
}

function normalizePath(path) {
  return String(path || "").replace(/^\/+/, "");
}

function pathSegments(path) {
  return normalizePath(path)
    .split("/")
    .filter(Boolean);
}

function isUnderscoreFolder(path) {
  return pathSegments(path)
    .slice(0, -1)
    .some(part => part.startsWith("_"));
}

function isExcludedPath(path, excludePaths = []) {
  const clean = normalizePath(path);

  if (!clean) return true;
  if (isUnderscoreFolder(clean)) return true;

  return excludePaths.some(prefix => {
    const cleanPrefix = normalizePath(prefix).replace(/\/+$/g, "");
    return cleanPrefix && (clean === cleanPrefix || clean.startsWith(`${cleanPrefix}/`));
  });
}

function titleForPage(page, fallback = "") {
  return (
    asText(page?.title) ||
    asText(fallback) ||
    asText(page?.file?.name) ||
    asText(page?.file?.path)
  );
}

function modifiedMillisForPage(page) {
  return page?.file?.mtime?.toMillis?.() ?? page?.file?.mtime ?? 0;
}

function modifiedDisplayForMillis(millis) {
  return millis && globalThis.window?.moment
    ? globalThis.window.moment(millis).format("YYYY-MM-DD HH:mm")
    : "";
}

function localeCompareText(a, b) {
  return String(a ?? "").localeCompare(String(b ?? ""), undefined, {
    sensitivity: "base",
  });
}

function alphaCompareRows(a, b) {
  return localeCompareText(a?.title || a?.name || a?.path, b?.title || b?.name || b?.path);
}

function isVaultRootFile(file) {
  const cleanPath = normalizePath(file?.path);
  return Boolean(cleanPath && !cleanPath.includes("/"));
}

function filenameTokens(file) {
  return String(file?.basename || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

function tocPriorityScore(file) {
  const basename = String(file?.basename || "").toLowerCase();
  const tokens = filenameTokens(file);
  const joined = tokens.join(" ");

  let score = 0;

  if (/^table\s+of\s+contents?$/.test(joined)) score += 100;
  if (tokens.includes("toc")) score += 90;
  if (tokens.includes("table")) score += 70;
  if (tokens.includes("contents")) score += 60;
  if (tokens.includes("content")) score += 50;

  if (basename.includes("toc")) score += 30;
  if (basename.includes("table")) score += 20;
  if (basename.includes("contents")) score += 15;
  if (basename.includes("content")) score += 10;

  return score;
}

function normalizeSlug(value) {
  return asText(value).toLowerCase().trim();
}

function slugPrefixForSlug(slug, slugPrefixes = [], fallback = "—") {
  const cleanSlug = normalizeSlug(slug);
  if (!cleanSlug) return fallback;

  const explicitPrefix = slugPrefixes.find(prefix => {
    const cleanPrefix = String(prefix || "").toLowerCase().trim();
    return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
  });

  if (explicitPrefix) return String(explicitPrefix).toLowerCase().trim();

  return cleanSlug.split(/[.\-_/]/)[0] || fallback;
}

function slugMatchesPrefixes(slug, slugPrefixes = []) {
  const cleanSlug = normalizeSlug(slug);
  if (!cleanSlug) return false;

  return slugPrefixes.some(prefix => {
    const cleanPrefix = String(prefix || "").toLowerCase().trim();
    return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
  });
}

function extractWikiLinks(line) {
  const links = [];
  const regex = /\[\[([^\]]+)\]\]/g;

  let match;
  while ((match = regex.exec(String(line || ""))) !== null) {
    const raw = match[1];
    const target = raw
      .split("|")[0]
      .split("#")[0]
      .trim();

    if (target) links.push(target);
  }

  return links;
}

function unicodeItemFromText(text, unicodeReference = []) {
  const cleanText = String(text || "")
    .trim()
    .replace(/^[-*+]\s+/, "")
    .replace(/^\d+[.)]\s+/, "")
    .trim();

  if (!cleanText) return null;

  return unicodeReference.find(entry => cleanText.startsWith(entry.symbol)) || null;
}

function unicodeFormatForText(text, unicodeReference = []) {
  return unicodeItemFromText(text, unicodeReference)?.label || "—";
}

function unicodeSymbolForText(text, unicodeReference = []) {
  return unicodeItemFromText(text, unicodeReference)?.symbol || "";
}

function unicodeDisplayForText(text, unicodeReference = []) {
  const item = unicodeItemFromText(text, unicodeReference);
  return item ? `${item.symbol} ${item.label}` : "—";
}

function headingKey(parts) {
  return parts
    .filter(Boolean)
    .map(part => String(part).trim())
    .join(" / ");
}

function headingLabel(parts, fallback = "Contents") {
  const clean = parts.filter(Boolean);
  return clean.length ? clean[clean.length - 1] : fallback;
}

function makeContentQueryUtils({ app, dv, config = {} } = {}) {
  const excludePaths = config.excludePaths || [];
  const slugPrefixes = config.slugPrefixes || [];
  const unicodeReference = config.unicodeReference || [];

  function isExcluded(path) {
    return isExcludedPath(path, excludePaths);
  }

  function pageForFile(file) {
    if (!file || isExcluded(file.path)) return null;
    return dv?.page(file.path) || null;
  }

  function candidateMarkdownFiles() {
    return app.vault.getMarkdownFiles()
      .filter(file => !isExcluded(file.path))
      .sort((a, b) => String(a.path).localeCompare(String(b.path)));
  }

  function resolveMarkdownFileFromWikiTarget(target, sourcePath) {
    const cleanTarget = String(target || "").replace(/\.md$/i, "").trim();
    if (!cleanTarget) return null;

    const linkDest = app.metadataCache.getFirstLinkpathDest(cleanTarget, sourcePath);
    if (linkDest) return linkDest;

    return app.vault.getMarkdownFiles().find(file =>
      file.basename === cleanTarget ||
      normalizePath(file.path) === normalizePath(`${cleanTarget}.md`)
    ) || null;
  }

  function getRootMarkdownCandidates() {
    return app.vault.getMarkdownFiles()
      .filter(file => isVaultRootFile(file))
      .filter(file => !isExcluded(file.path))
      .sort((a, b) => {
        const scoreDiff = tocPriorityScore(b) - tocPriorityScore(a);
        if (scoreDiff !== 0) return scoreDiff;

        return String(a.name).localeCompare(String(b.name));
      });
  }

  return {
    asText,
    asList,
    normalizePath,
    pathSegments,
    isUnderscoreFolder,
    isExcludedPath: isExcluded,
    titleForPage,
    modifiedMillisForPage,
    modifiedDisplayForMillis,
    localeCompareText,
    alphaCompareRows,
    isVaultRootFile,
    filenameTokens,
    tocPriorityScore,
    getRootMarkdownCandidates,
    normalizeSlug,
    slugPrefixForSlug: (slug, fallback = "—") => slugPrefixForSlug(slug, slugPrefixes, fallback),
    slugMatchesCriteria: slug => slugMatchesPrefixes(slug, slugPrefixes),
    extractWikiLinks,
    resolveMarkdownFileFromWikiTarget,
    unicodeItemFromText: text => unicodeItemFromText(text, unicodeReference),
    unicodeFormatForText: text => unicodeFormatForText(text, unicodeReference),
    unicodeSymbolForText: text => unicodeSymbolForText(text, unicodeReference),
    unicodeDisplayForText: text => unicodeDisplayForText(text, unicodeReference),
    headingKey,
    headingLabel,
    pageForFile,
    candidateMarkdownFiles,
  };
}

module.exports = {
  asText,
  asList,
  normalizePath,
  pathSegments,
  isUnderscoreFolder,
  isExcludedPath,
  titleForPage,
  modifiedMillisForPage,
  modifiedDisplayForMillis,
  localeCompareText,
  alphaCompareRows,
  isVaultRootFile,
  filenameTokens,
  tocPriorityScore,
  normalizeSlug,
  slugPrefixForSlug,
  slugMatchesPrefixes,
  extractWikiLinks,
  unicodeItemFromText,
  unicodeFormatForText,
  unicodeSymbolForText,
  unicodeDisplayForText,
  headingKey,
  headingLabel,
  makeContentQueryUtils,
};
