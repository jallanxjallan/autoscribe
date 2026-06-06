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

function parseJsonStringMaybe(value, fieldName) {
  if (typeof value !== "string") return value;

  const text = value.trim();
  if (!text) return value;

  if (
    (text.startsWith("{") && text.endsWith("}")) ||
    (text.startsWith("[") && text.endsWith("]"))
  ) {
    try {
      return JSON.parse(text);
    } catch (error) {
      throw new Error(`${fieldName}: invalid JSON string: ${error.message}`);
    }
  }

  return value;
}

function flattenFieldPairs(value, options = {}) {
  const {
    sourceName = "record",
    parseJsonStrings = true,
  } = options;

  const flat = {};
  const seen = new Map();

  function addField(key, fieldValue, path) {
    if (!key) return;

    if (Object.prototype.hasOwnProperty.call(flat, key)) {
      const firstPath = seen.get(key);
      throw new Error(`${sourceName}: duplicate field name "${key}" at ${firstPath} and ${path}`);
    }

    flat[key] = fieldValue;
    seen.set(key, path);
  }

  function walk(node, path) {
    const parsed = parseJsonStrings ? parseJsonStringMaybe(node, path) : node;

    if (Array.isArray(parsed)) {
      parsed.forEach((item, index) => walk(item, `${path}[${index}]`));
      return;
    }

    if (!isPlainObject(parsed)) return;

    for (const [key, child] of Object.entries(parsed)) {
      const childPath = path ? `${path}.${key}` : key;
      const parsedChild = parseJsonStrings ? parseJsonStringMaybe(child, childPath) : child;

      if (isPlainObject(parsedChild) || Array.isArray(parsedChild)) {
        walk(parsedChild, childPath);
      } else {
        addField(key, parsedChild, childPath);
      }
    }
  }

  walk(value, sourceName);
  return flat;
}

function flattenRecord(record) {
  if (!isPlainObject(record)) {
    throw new Error("record must be a JSON object");
  }

  return flattenFieldPairs(record, {
    sourceName: "record",
    parseJsonStrings: true,
  });
}

function requireStringField(flat, key, label = key) {
  const value = flat[key];

  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`missing ${label}`);
  }

  return value.trim();
}

function normalizePendingRecord(record, index) {
  const flat = flattenRecord(record);

  const promptSlug = requireStringField(flat, "prompt_slug", `prompt_slug in pending record ${index + 1}`);
  const callIdentity = requireStringField(flat, "call_identity", `call_identity in pending record ${index + 1}`);
  const resultIdentity = requireStringField(flat, "result_identity", `result_identity in pending record ${index + 1}`);

  const slugRe = new RegExp(`^${slugRegexText()}$`);
  const identityRe = new RegExp(`^${identityRegexText()}$`);

  if (!slugRe.test(promptSlug)) {
    throw new Error(`pending record ${index + 1}: invalid prompt_slug: ${promptSlug}`);
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
    flat,
    raw: record,
  };
}

function parsePendingRecords(text) {
  return parseNdjson(text).map(normalizePendingRecord);
}

function extractPayloadFromStdout(stdout) {
  const records = parseNdjson(stdout);

  if (records.length !== 1) {
    throw new Error(`expected exactly one extracted result record, got ${records.length}`);
  }

  const record = records[0];
  const flat = flattenRecord(record);
  const content = requireStringField(flat, "content", "content in extracted result record");

  return {
    content,
    flat,
    raw: record,
  };
}

module.exports = {
  identityRegexText,
  parseNdjson,
  flattenFieldPairs,
  flattenRecord,
  parsePendingRecords,
  extractPayloadFromStdout,
};
