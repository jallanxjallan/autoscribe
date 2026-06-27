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

function normalizeWritebackRecord(record, index) {
  requireRecordObject(record, index, "writeback record");

  const promptSlug = requireStringField(
    record,
    "record_identity",
    `record_identity in writeback record ${index + 1}`
  );

  const content = requireStringField(
    record,
    "record_content",
    `record_content in writeback record ${index + 1}`
  );

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
};
