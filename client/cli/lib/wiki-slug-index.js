"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { getFrontmatterTextFromMarkdown } = require("./markdown");
const { buildSlugPathMap } = require("./rg");
const { slugPrefix, assertUniqueSlugRecords } = require("./slug");
const {
  normalizeWikiTarget,
  wikiAliasesForRecord,
} = require("./wikilinks");

const DEFAULT_PUBLIC_SLUG_PREFIXES = ["drv", "ins", "job", "gbl", "cxt", "spc"];

function addIndexRecord(map, key, record) {
  const normalized = normalizeWikiTarget(key);
  if (!normalized) return;

  const existing = map.get(normalized) || [];
  if (!existing.some((item) => item.path === record.path && item.slug === record.slug)) {
    existing.push(record);
  }
  map.set(normalized, existing);
}

function collectAllPublicSlugRecords({
  root,
  prefixes = DEFAULT_PUBLIC_SLUG_PREFIXES,
  rg,
} = {}) {
  if (!root) throw new Error("collectAllPublicSlugRecords requires root.");

  const { bySlug } = buildSlugPathMap({ root, prefixes, rg });
  const records = [];

  for (const record of bySlug.values()) {
    const absPath = path.join(root, record.path);
    const markdown = fs.readFileSync(absPath, "utf8");
    const slug = getFrontmatterTextFromMarkdown(markdown, "slug") || record.slug;
    if (!slug) continue;

    records.push({
      slug,
      prefix: slugPrefix(slug),
      path: record.path,
    });
  }

  assertUniqueSlugRecords(records, { label: "vault slug" });
  records.sort((a, b) => a.path.localeCompare(b.path));
  return records;
}

function buildWikiSlugIndex({ root, prefixes = DEFAULT_PUBLIC_SLUG_PREFIXES, rg } = {}) {
  const records = collectAllPublicSlugRecords({ root, prefixes, rg });
  const exact = new Map();
  const lower = new Map();

  for (const record of records) {
    for (const alias of wikiAliasesForRecord(record)) {
      addIndexRecord(exact, alias, record);
      addIndexRecord(lower, alias.toLowerCase(), record);
    }
  }

  return { exact, lower, records };
}

function formatResolutionCandidates(records) {
  return records.map((record) => `${record.slug} (${record.path})`).join("; ");
}

function resolveWikiTarget({ index, target, context = "wikilink" }) {
  const normalized = normalizeWikiTarget(target);
  if (!normalized) throw new Error(`${context}: empty wikilink target`);

  const exactMatches = index.exact.get(normalized) || [];
  if (exactMatches.length === 1) return exactMatches[0];
  if (exactMatches.length > 1) {
    throw new Error(`${context}: ambiguous wikilink [[${target}]]: ${formatResolutionCandidates(exactMatches)}`);
  }

  const lowerMatches = index.lower.get(normalized.toLowerCase()) || [];
  if (lowerMatches.length === 1) return lowerMatches[0];
  if (lowerMatches.length > 1) {
    throw new Error(`${context}: ambiguous wikilink [[${target}]]: ${formatResolutionCandidates(lowerMatches)}`);
  }

  throw new Error(`${context}: unresolved wikilink [[${target}]]`);
}

module.exports = {
  DEFAULT_PUBLIC_SLUG_PREFIXES,
  collectAllPublicSlugRecords,
  buildWikiSlugIndex,
  resolveWikiTarget,
};
