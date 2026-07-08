'use strict';

const { runWritingCommand } = require("./core");
const {
  absVaultPath,
  assertCleanTrackedTarget,
  isDirty,
} = require("./vault");
const { parseWritebackRecords } = require("./pending");
const { composeMarkdownFromExistingFrontmatter } = require("./markdown");

const fs = require("node:fs");

function fail(script, message) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(1);
}

function info(script, message) {
  console.error(`${script}: ${message}`);
}

function selectWritebackCandidates({ root, vaultSlugs, pendingExports, script }) {
  const items = [];
  const missing = [];

  for (const pending of pendingExports) {
    const target = vaultSlugs.get(pending.promptSlug);

    if (!target) {
      missing.push(pending);
      continue;
    }

    items.push({
      ...pending,
      path: target.path,
      lineNumber: target.lineNumber,
    });
  }

  const bySlug = new Map();
  const duplicateTargets = new Map();

  for (const item of items) {
    if (bySlug.has(item.promptSlug)) {
      const list = duplicateTargets.get(item.promptSlug) || [bySlug.get(item.promptSlug)];
      list.push(item);
      duplicateTargets.set(item.promptSlug, list);
    } else {
      bySlug.set(item.promptSlug, item);
    }
  }

  if (duplicateTargets.size > 0) {
    const lines = ["multiple pending results target the same vault slug:"];

    for (const [slug, records] of duplicateTargets.entries()) {
      lines.push(`  ${slug}`);
      for (const record of records) {
        lines.push(`    - call ${record.callIdentity}, result ${record.resultIdentity} -> ${record.path}`);
      }
    }

    fail(script, lines.join("\n"));
  }

  items.sort((a, b) => a.path.localeCompare(b.path));
  missing.sort((a, b) => a.promptSlug.localeCompare(b.promptSlug));

  for (const item of items) {
    assertCleanTrackedTarget({ root, relPath: item.path, script });
  }

  const summaryLines = [`writeback candidates: ${items.length}`];

  if (missing.length > 0) {
    summaryLines.push(`pending export slugs not found in this vault: ${missing.length}`);

    for (const item of missing.slice(0, 20)) {
      summaryLines.push(`  no target: ${item.promptSlug} (call ${item.callIdentity}, result ${item.resultIdentity})`);
    }

    if (missing.length > 20) {
      summaryLines.push(`  ... ${missing.length - 20} more`);
    }
  }

  return {
    items,
    missing,
    summaryLines,
  };
}

function applyWritebackItem({ root, item, options, script }) {
  if (isDirty({ root, relPath: item.path })) {
    fail(script, `${item.path}: target file became dirty before writeback; aborting`);
  }

  const fullPath = absVaultPath(root, item.path);
  const targetMarkdown = fs.readFileSync(fullPath, "utf8");

  const nextMarkdown = composeMarkdownFromExistingFrontmatter({
    targetMarkdown,
    resultContent: item.content,
    relPath: item.path,
    script,
  });

  const normalizedTargetMarkdown = targetMarkdown.replace(/\r\n/g, "\n");

  if (nextMarkdown === normalizedTargetMarkdown) {
    info(script, `unchanged: ${item.promptSlug} -> ${item.path}`);

    return {
      ...item,
      changed: false,
    };
  }

  fs.writeFileSync(fullPath, nextMarkdown, "utf8");

  info(script, `wrote: ${item.promptSlug} -> ${item.path}`);

  return {
    ...item,
    changed: true,
  };
}


function readStdinText({ script }) {
  if (process.stdin.isTTY) {
    fail(script, "expected piped NDJSON on stdin from asc export extract-result/export-result");
  }

  process.stdin.setEncoding("utf8");

  return new Promise((resolve, reject) => {
    let text = "";

    process.stdin.on("data", chunk => {
      text += chunk;
    });

    process.stdin.on("end", () => {
      resolve(text);
    });

    process.stdin.on("error", error => {
      reject(error);
    });
  });
}

function parseWritebackInput(text, { script }) {
  try {
    return parseWritebackRecords(text);
  } catch (error) {
    fail(script, `could not parse writeback input: ${error.message}`);
  }
}

async function main() {
  const script = "writeback";
  let text;

  try {
    text = await readStdinText({ script });
  } catch (error) {
    fail(script, `could not read writeback input: ${error.message}`);
  }

  const inputRecords = parseWritebackInput(text, { script });

  return runWritingCommand({
    script,
    mode: "writeback",
    defaultTargetDir: null,
    inputLabel: "writeback input records",
    marksExports: false,
    loadInputRecords: () => inputRecords,
    selectCandidates: selectWritebackCandidates,
    applyItem: applyWritebackItem,
  });
}

module.exports = {
  main,
  selectWritebackCandidates,
  applyWritebackItem,
};

if (require.main === module) {
  main().catch(error => {
    console.error(`writeback: ERROR: ${error.message}`);
    process.exit(1);
  });
}
