const { kebabCase, normalizeScalar } = require("./text");

function slugRegexText() {
  return "[a-z][a-z0-9-]*\\.[a-z0-9][a-z0-9-]*\\.[a-z0-9]*[0-9][a-z0-9]*";
}

function slugPrefix(slug) {
  const text = String(slug || "").trim();
  if (!text) return "";
  return text.split(".")[0] || "";
}

function normalizeSlugPrefix(value, options = {}) {
  return kebabCase(value, {
    fallback: "",
    maxLength: 16,
    ...options,
  });
}

function slugMiddle(value, options = {}) {
  return kebabCase(value, {
    fallback: "note",
    maxLength: 48,
    ...options,
  });
}

function randomSlugIdentity(length = 6) {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";

  while (true) {
    let out = "";

    for (let index = 0; index < length; index += 1) {
      out += alphabet[Math.floor(Math.random() * alphabet.length)];
    }

    if (/\d/.test(out)) return out;
  }
}

function normalizeSlugIdentity(value) {
  return normalizeScalar(value)
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function slugFromParts(prefix, middle, identity = "") {
  const cleanPrefix = normalizeSlugPrefix(prefix);
  const cleanMiddle = slugMiddle(middle);
  const cleanIdentity = normalizeSlugIdentity(identity) || randomSlugIdentity();

  if (!cleanPrefix) {
    throw new Error("slugFromParts requires a prefix.");
  }

  if (!/\d/.test(cleanIdentity)) {
    throw new Error("slugFromParts requires an identity containing at least one digit.");
  }

  return `${cleanPrefix}.${cleanMiddle}.${cleanIdentity}`;
}

function makeSlug(prefix, hint, options = {}) {
  const { identity = "", identityLength = 6 } = options;

  if (identity) {
    return slugFromParts(prefix, hint, identity);
  }

  return slugFromParts(prefix, hint, randomSlugIdentity(identityLength));
}

function assertNoDuplicateSlugs(duplicateSlugs, options = {}) {
  const { label = "slug", includePaths = true } = options;

  if (!duplicateSlugs || duplicateSlugs.size === 0) return;

  const lines = [`Duplicate ${label}s found:`];

  for (const [slug, records] of duplicateSlugs.entries()) {
    lines.push(`  ${slug}`);

    if (includePaths) {
      for (const record of records || []) {
        const location = record.path || record.file?.path || record.name || "unknown path";
        lines.push(`    - ${location}`);
      }
    }
  }

  throw new Error(lines.join("\n"));
}

function assertUniqueSlugRecords(records, options = {}) {
  const duplicateSlugs = new Map();
  const bySlug = new Map();

  for (const record of records || []) {
    const slug = String(record?.slug || "").trim();
    if (!slug) continue;

    if (bySlug.has(slug)) {
      const list = duplicateSlugs.get(slug) || [bySlug.get(slug)];
      list.push(record);
      duplicateSlugs.set(slug, list);
    } else {
      bySlug.set(slug, record);
    }
  }

  assertNoDuplicateSlugs(duplicateSlugs, options);
}

module.exports = {
  slugRegexText,
  slugPrefix,
  normalizeSlugPrefix,
  slugMiddle,
  randomSlugIdentity,
  normalizeSlugIdentity,
  slugFromParts,
  makeSlug,
  assertNoDuplicateSlugs,
  assertUniqueSlugRecords,
};
