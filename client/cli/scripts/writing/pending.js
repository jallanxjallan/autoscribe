const { slugRegexText } = require("../../lib/slug");

function identityRegexText() {
  return "[0-9A-HJKMNP-TV-Z]{20,32}";
}

function parseNdjson(text) {
  const records = [];

  for (const line of String(text || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    records.push(JSON.parse(trimmed));
  }

  return records;
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireRecordObject(record, index, label) {
  if (!isPlainObject(record)) {
    throw new Error(`${label} ${index + 1}: expected a JSON object`);
  }
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }

  return "";
}

function requireStringField(record, key, label = key) {
  const value = record[key];

  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`missing ${label}`);
  }

  return value.trim();
}

function parseJsonObjectString(value) {
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  if (!trimmed.startsWith("{")) return null;

  try {
    const parsed = JSON.parse(trimmed);
    return isPlainObject(parsed) ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function firstPresentContentValue(record) {
  for (const key of ["record_content", "result_content", "content", "body", "text"]) {
    const value = record[key];

    if (isPlainObject(value)) {
      return value;
    }

    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }

  return "";
}

function parseJsonObjectOrString(value) {
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  if (!trimmed.startsWith("{") && !trimmed.startsWith('"')) return null;

  try {
    return JSON.parse(trimmed);
  } catch (_error) {
    return null;
  }
}

function parseSingleNdjsonObject(value) {
  if (typeof value !== "string") return null;

  const lines = value
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);

  if (lines.length !== 1) return null;

  const parsed = parseJsonObjectString(lines[0]);
  return isPlainObject(parsed) ? parsed : null;
}

function extractRecordContent(value, seen = new Set()) {
  if (isPlainObject(value)) {
    return extractRecordContent(firstPresentContentValue(value), seen);
  }

  if (typeof value !== "string" || !value.trim()) {
    return "";
  }

  const trimmed = value.trim();

  if (seen.has(trimmed)) {
    return trimmed;
  }
  seen.add(trimmed);

  const parsedSingleLine = parseSingleNdjsonObject(trimmed);
  if (parsedSingleLine) {
    const nestedContent = extractRecordContent(firstPresentContentValue(parsedSingleLine), seen);
    if (nestedContent && nestedContent !== trimmed) return nestedContent;
  }

  const parsed = parseJsonObjectOrString(trimmed);
  if (isPlainObject(parsed)) {
    const nestedContent = extractRecordContent(firstPresentContentValue(parsed), seen);
    if (nestedContent && nestedContent !== trimmed) return nestedContent;
  }

  if (typeof parsed === "string" && parsed.trim()) {
    const nestedContent = extractRecordContent(parsed, seen);
    if (nestedContent && nestedContent !== trimmed) return nestedContent;
  }

  return trimmed;
}

function requireRecordContent(record, index) {
  const content = extractRecordContent(firstPresentContentValue(record));

  if (!content) {
    throw new Error(`missing record_content in writeback record ${index + 1}`);
  }

  return content;
}

function normalizeWritebackRecord(record, index) {
  requireRecordObject(record, index, "writeback record");

  const promptSlug = requireStringField(
    record,
    "record_identity",
    `record_identity in writeback record ${index + 1}`
  );

  const content = requireRecordContent(record, index);

  const slugRe = new RegExp(`^${slugRegexText()}$`);

  if (!slugRe.test(promptSlug)) {
    throw new Error(`writeback record ${index + 1}: invalid record_identity: ${promptSlug}`);
  }

  return {
    promptSlug,
    recordIdentity: promptSlug,
    content,
    resultIdentity: firstString(record.result_identity),
    raw: record,
  };
}

function parseWritebackRecords(text) {
  return parseNdjson(text).map(normalizeWritebackRecord);
}

function normalizePendingRecord(record, index) {
  requireRecordObject(record, index, "pending record");

  const promptSlug = firstString(record.record_identity, record.prompt_slug);
  const callIdentity = firstString(record.call_identity);
  const resultIdentity = firstString(record.result_identity);

  if (!promptSlug) {
    throw new Error(`missing record_identity in pending record ${index + 1}`);
  }

  if (!callIdentity) {
    throw new Error(`missing call_identity in pending record ${index + 1}`);
  }

  if (!resultIdentity) {
    throw new Error(`missing result_identity in pending record ${index + 1}`);
  }

  const slugRe = new RegExp(`^${slugRegexText()}$`);
  const identityRe = new RegExp(`^${identityRegexText()}$`);

  if (!slugRe.test(promptSlug)) {
    throw new Error(`pending record ${index + 1}: invalid record_identity: ${promptSlug}`);
  }

  if (!identityRe.test(callIdentity)) {
    throw new Error(`pending record ${index + 1}: invalid call_identity: ${callIdentity}`);
  }

  if (!identityRe.test(resultIdentity)) {
    throw new Error(`pending record ${index + 1}: invalid result_identity: ${resultIdentity}`);
  }

  return {
    promptSlug,
    callIdentity,
    resultIdentity,
    raw: record,
  };
}

function parsePendingRecords(text) {
  return parseNdjson(text).map(normalizePendingRecord);
}

function extractPayloadFromStdout(stdout) {
  const records = parseWritebackRecords(stdout);

  if (records.length !== 1) {
    throw new Error(`expected exactly one extracted result record, got ${records.length}`);
  }

  const record = records[0];

  return {
    content: record.content,
    raw: record.raw,
  };
}

module.exports = {
  identityRegexText,
  parseNdjson,
  parsePendingRecords,
  parseWritebackRecords,
  extractPayloadFromStdout,
  extractRecordContent,
};
