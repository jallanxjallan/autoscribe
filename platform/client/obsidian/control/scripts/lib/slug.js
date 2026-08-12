const crypto = require('crypto');

function kebab(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'untitled';
}

function shortId() {
  // Six lowercase base36-ish chars, with at least one digit.
  const raw = crypto.randomBytes(5).toString('base64url').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 6);
  const padded = (raw + '000000').slice(0, 6);
  return /\d/.test(padded) ? padded : `${padded.slice(0, 5)}0`;
}

function makeSlug(prefix, label) {
  return `${prefix}.${kebab(label)}.${shortId()}`;
}

function buildSlugIndex(app, { prefixes = [], excludePaths = [] } = {}) {
  const records = [];
  const bySlug = new Map();
  const byPath = new Map();
  const duplicateSlugs = new Set();

  const allowedPrefixes = new Set(prefixes || []);
  const excluded = new Set(excludePaths || []);

  for (const file of app.vault.getMarkdownFiles()) {
    const path = file.path;
    if (excluded.has(path)) continue;

    const fm = app.metadataCache.getFileCache(file)?.frontmatter || {};
    const slug = String(fm.slug || "").trim();
    if (!slug) continue;

    const prefix = slug.split(".")[0] || "";
    if (allowedPrefixes.size && !allowedPrefixes.has(prefix)) continue;

    const record = {
      file,
      path,
      name: file.name,
      basename: file.basename,
      slug,
      prefix,
      mtime: file.stat?.mtime ?? 0,
    };

    if (bySlug.has(slug)) duplicateSlugs.add(slug);
    bySlug.set(slug, record);
    byPath.set(path, record);
    records.push(record);
  }

  return { records, bySlug, byPath, duplicateSlugs };
}

module.exports = { kebab, makeSlug, buildSlugIndex };
