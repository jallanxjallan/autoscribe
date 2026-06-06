'use strict';

const { runWritingCommand } = require("./core");
const {
  absVaultPath,
  assertCleanTrackedTarget,
  isDirty,
} = require("./vault");
const {
  extractResultPayload,
  markResultExported,
} = require("./asc");
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

  const exported = extractResultPayload({
    root,
    ascBin: options.ascBin,
    item,
    script,
  });

  const nextMarkdown = composeMarkdownFromExistingFrontmatter({
    targetMarkdown,
    resultContent: exported.content,
    relPath: item.path,
    script,
  });

  const normalizedTargetMarkdown = targetMarkdown.replace(/\r\n/g, "\n");

  if (nextMarkdown === normalizedTargetMarkdown) {
    markResultExported({
      root,
      ascBin: options.ascBin,
      resultIdentity: item.resultIdentity,
      script,
    });

    info(script, `unchanged: ${item.promptSlug} -> ${item.path}`);

    return {
      ...item,
      changed: false,
      extractionIdentity: exported.extractionIdentity,
      extractionIdentityKind: exported.extractionIdentityKind,
    };
  }

  fs.writeFileSync(fullPath, nextMarkdown, "utf8");

  markResultExported({
    root,
    ascBin: options.ascBin,
    resultIdentity: item.resultIdentity,
    script,
  });

  info(script, `wrote: ${item.promptSlug} -> ${item.path}`);

  return {
    ...item,
    changed: true,
    extractionIdentity: exported.extractionIdentity,
    extractionIdentityKind: exported.extractionIdentityKind,
  };
}

function main() {
  return runWritingCommand({
    script: "writeback",
    mode: "writeback",
    defaultTargetDir: null,
    selectCandidates: selectWritebackCandidates,
    applyItem: applyWritebackItem,
  });
}

module.exports = {
  main,
  selectWritebackCandidates,
  applyWritebackItem,
};

if (require.main === module) main();
