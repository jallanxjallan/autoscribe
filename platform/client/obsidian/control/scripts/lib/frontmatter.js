const DEFAULT_MISSING = "—";

function normalizeValue(value, missing = DEFAULT_MISSING) {
  if (value === null || value === undefined) return missing;

  if (Array.isArray(value)) {
    const cleaned = value.map(v => String(v).trim()).filter(Boolean);
    return cleaned.length ? cleaned.join(", ") : missing;
  }

  const text = String(value).trim();
  return text ? text : missing;
}

function getFrontmatter(app, file) {
  return app.metadataCache.getFileCache(file)?.frontmatter ?? {};
}

function getFrontmatterJson(app, file) {
  return JSON.stringify(getFrontmatter(app, file));
}

function getFrontmatterEntry(app, file, key) {
  const frontmatter = getFrontmatter(app, file);
  const entry = Object.entries(frontmatter).find(
    ([k]) => String(k).toLowerCase() === String(key).toLowerCase()
  );

  return entry?.[1];
}

function getFrontmatterValue(app, file, key, missing = DEFAULT_MISSING) {
  return normalizeValue(getFrontmatterEntry(app, file, key), missing);
}

function getOptionalFrontmatterText(app, file, key) {
  const value = getFrontmatterEntry(app, file, key);

  if (value === null || value === undefined) {
    return "";
  }

  return String(value).trim();
}

module.exports = {
  DEFAULT_MISSING,
  normalizeValue,
  getFrontmatter,
  getFrontmatterJson,
  getFrontmatterEntry,
  getFrontmatterValue,
  getOptionalFrontmatterText,
};