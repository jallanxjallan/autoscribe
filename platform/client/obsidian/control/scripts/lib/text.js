function asText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function normalizeScalar(value, fallback = "") {
  return asText(value, fallback).trim();
}

function normalizeWhitespace(value, fallback = "") {
  return normalizeScalar(value, fallback).replace(/\s+/g, " ");
}

function stripDiacritics(value) {
  return asText(value)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "");
}

function kebabCase(value, options = {}) {
  const {
    fallback = "note",
    maxLength = 48
  } = options;

  const text = stripDiacritics(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");

  const clipped = maxLength
    ? text.slice(0, maxLength).replace(/-+$/g, "")
    : text;

  return clipped || fallback;
}

function normalizeFolder(folder) {
  return normalizeScalar(folder)
    .replace(/^\/+|\/+$/g, "")
    .replace(/\/+/g, "/");
}

function sanitizeForPath(value, options = {}) {
  const {
    fallback = "unknown",
    maxLength = 90
  } = options;

  const text = stripDiacritics(value)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");

  const clipped = maxLength
    ? text.slice(0, maxLength).replace(/-+$/g, "")
    : text;

  return clipped || fallback;
}

function sortText(values) {
  return [...values].sort((a, b) =>
    String(a).localeCompare(String(b), undefined, { sensitivity: "base" })
  );
}

function titleCase(value) {
  return normalizeWhitespace(value)
    .toLowerCase()
    .split(" ")
    .filter(Boolean)
    .map((word) => {
      if (/^[a-z]\d|\d/.test(word)) return word;
      return `${word.slice(0, 1).toUpperCase()}${word.slice(1)}`;
    })
    .join(" ");
}

function titleCaseStem(value) {
  return titleCase(
    asText(value)
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
  );
}

module.exports = {
  asText,
  normalizeScalar,
  normalizeWhitespace,
  stripDiacritics,
  kebabCase,
  normalizeFolder,
  sanitizeForPath,
  sortText,
  titleCase,
  titleCaseStem
};