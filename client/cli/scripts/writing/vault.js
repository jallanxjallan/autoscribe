const fs = require("node:fs");
const path = require("node:path");

const {
  getGitRoot,
  listDirtyTrackedFiles,
  hasEverBeenCommitted,
} = require("../../lib/git");

const { findSlugLines } = require("../../lib/rg");
const { isPublicVaultPath } = require("../../lib/query-paths");
const { assertUniqueSlugRecords } = require("../../lib/slug");

function fail(script, message) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(1);
}

function normalizeRelPath(relPath) {
  return String(relPath || "")
    .replace(/\\/g, "/")
    .replace(/^\.\//, "");
}

function getVaultRoot(cwd = process.cwd()) {
  return getGitRoot(cwd);
}

function assertVaultRoot({ root, script }) {
  if (!root) fail(script, "could not resolve git root");

  const obsidianDir = path.join(root, ".obsidian");
  if (!fs.existsSync(obsidianDir) || !fs.statSync(obsidianDir).isDirectory()) {
    fail(script, `git root is not an Obsidian vault: ${root}`);
  }

  const controlPath = path.join(root, "_control");
  if (!fs.existsSync(controlPath)) {
    fail(script, `refusing to run without _control in vault root: ${root}`);
  }
}

function absVaultPath(root, relPath) {
  return path.join(root, ...normalizeRelPath(relPath).split("/"));
}

function gatherVaultSlugs({ root, script }) {
  const records = [];

  for (const line of findSlugLines({ root })) {
    const match = line.match(/^(.+?):(\d+):\s*slug:\s*(\S+)\s*$/);
    if (!match) continue;

    const [, rawPath, rawLineNumber, slug] = match;
    const relPath = normalizeRelPath(rawPath);

    if (!isPublicVaultPath(relPath)) continue;

    records.push({
      slug,
      path: relPath,
      lineNumber: Number(rawLineNumber),
    });
  }

  try {
    assertUniqueSlugRecords(records, { label: "vault slug" });
  } catch (error) {
    fail(script, error.message || String(error));
  }

  records.sort((a, b) => a.path.localeCompare(b.path));
  return new Map(records.map(record => [record.slug, record]));
}

function dirtyTrackedPathSet({ root }) {
  return new Set(
    listDirtyTrackedFiles({ root })
      .map(normalizeRelPath)
      .filter(relPath => relPath.endsWith(".md"))
      .filter(isPublicVaultPath)
  );
}

function isDirty({ root, relPath }) {
  return dirtyTrackedPathSet({ root }).has(normalizeRelPath(relPath));
}

function assertCleanTrackedTarget({ root, relPath, script }) {
  const normalized = normalizeRelPath(relPath);
  const fullPath = absVaultPath(root, normalized);

  if (!fs.existsSync(fullPath) || !fs.statSync(fullPath).isFile()) {
    fail(script, `${normalized}: target file not found`);
  }

  if (!hasEverBeenCommitted({ root, path: normalized })) {
    fail(script, `${normalized}: target file has never been committed`);
  }

  if (isDirty({ root, relPath: normalized })) {
    fail(script, `${normalized}: target file is already dirty`);
  }
}

function resolveVaultRelativeDir({ root, targetDirArg, script }) {
  const raw = String(targetDirArg || "new").trim() || "new";

  if (path.isAbsolute(raw)) {
    fail(script, `target dir must be vault-relative: ${raw}`);
  }

  const normalized = normalizeRelPath(raw).replace(/\/+$/, "") || "new";
  const absolute = path.resolve(root, normalized);
  const rootWithSep = root.endsWith(path.sep) ? root : `${root}${path.sep}`;

  if (absolute !== root && !absolute.startsWith(rootWithSep)) {
    fail(script, `target dir escapes vault root: ${raw}`);
  }

  if (fs.existsSync(absolute) && !fs.statSync(absolute).isDirectory()) {
    fail(script, `target dir exists but is not a directory: ${normalized}`);
  }

  return {
    relative: normalizeRelPath(path.relative(root, absolute)) || ".",
    absolute,
  };
}

function targetExists(root, relPath) {
  return fs.existsSync(absVaultPath(root, relPath));
}

module.exports = {
  normalizeRelPath,
  getVaultRoot,
  assertVaultRoot,
  absVaultPath,
  gatherVaultSlugs,
  dirtyTrackedPathSet,
  isDirty,
  assertCleanTrackedTarget,
  resolveVaultRelativeDir,
  targetExists,
};
