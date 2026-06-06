const {
  parsePendingRecords,
  extractPayloadFromStdout,
} = require("./pending");

const { spawnSync } = require("node:child_process");

const MAX_BUFFER = 50 * 1024 * 1024;

function fail(script, message) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(1);
}

function runAsc({ ascBin, args, cwd, script }) {
  const result = spawnSync(ascBin, args, {
    cwd,
    env: process.env,
    encoding: "utf8",
    shell: false,
    maxBuffer: MAX_BUFFER,
  });

  const rendered = [ascBin, ...args].join(" ");

  if (result.error) {
    fail(script, `${rendered}: ${result.error.message}`);
  }

  const status = result.status ?? 0;

  if (status !== 0) {
    const stderr = String(result.stderr || "").trim();
    const stdout = String(result.stdout || "").trim();
    const detail = stderr || stdout || `exit status ${status}`;
    fail(script, `${rendered} failed: ${detail}`);
  }

  return {
    stdout: result.stdout || "",
    stderr: result.stderr || "",
  };
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }

  return "";
}

function normalizePendingItem(item, index = 0) {
  const flat = item?.flat && typeof item.flat === "object"
    ? item.flat
    : {};

  const promptSlug = firstString(
    item?.promptSlug,
    item?.prompt_slug,
    flat.prompt_slug
  );

  const callIdentity = firstString(
    item?.callIdentity,
    item?.call_identity,
    flat.call_identity
  );

  const resultIdentity = firstString(
    item?.resultIdentity,
    item?.result_identity,
    flat.result_identity
  );

  if (!promptSlug) {
    throw new Error(`pending item ${index + 1}: missing prompt slug`);
  }

  if (!callIdentity) {
    throw new Error(`pending item ${index + 1}: missing call identity`);
  }

  if (!resultIdentity) {
    throw new Error(`pending item ${index + 1}: missing result identity`);
  }

  return {
    promptSlug,
    callIdentity,
    resultIdentity,
    flat,
    raw: item?.raw ?? item,
  };
}

function listPendingExports({ root, ascBin, script }) {
  const result = runAsc({
    ascBin,
    args: ["export", "list-pending-exports"],
    cwd: root,
    script,
  });

  let records;

  try {
    records = parsePendingRecords(result.stdout).map(normalizePendingItem);
  } catch (error) {
    fail(script, `could not parse pending exports: ${error.message}`);
  }

  const byResultIdentity = new Map();

  for (const record of records) {
    if (!byResultIdentity.has(record.resultIdentity)) {
      byResultIdentity.set(record.resultIdentity, record);
    }
  }

  return [...byResultIdentity.values()];
}

function extractResultPayload({ root, ascBin, item, script }) {
  const pending = normalizePendingItem(item);

  const result = runAsc({
    ascBin,
    args: ["export", "extract-result", pending.callIdentity],
    cwd: root,
    script,
  });

  let payload;

  try {
    // The new pending parser/extractor can ignore the second argument.
    // The older extractor can still use it to select the expected record.
    payload = extractPayloadFromStdout(result.stdout, pending);
  } catch (error) {
    fail(
      script,
      `${pending.promptSlug}: could not parse extracted result for ${pending.callIdentity}: ${error.message}`
    );
  }

  if (!payload.content || !payload.content.trim()) {
    const stderr = String(result.stderr || "").trim();
    const detail = stderr ? ` stderr: ${stderr}` : "";

    fail(
      script,
      `${pending.promptSlug}: asc export extract-result ${pending.callIdentity} returned no content.${detail}`
    );
  }

  return {
    content: payload.content,
    flat: payload.flat ?? {},
    raw: payload.raw,
    extractionIdentity: pending.callIdentity,
    extractionIdentityKind: "call_identity",
    pending,
  };
}

function markResultExported({ root, ascBin, resultIdentity, script }) {
  runAsc({
    ascBin,
    args: ["export", "update-exports", resultIdentity],
    cwd: root,
    script,
  });
}

module.exports = {
  listPendingExports,
  extractResultPayload,
  markResultExported,
};