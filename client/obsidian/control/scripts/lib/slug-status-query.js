const { buildSlugIndex } = require("./slug");
const { getFrontmatterValue } = require("./frontmatter");
const { formatRelativeTime } = require("./time");
const { publicSlugRecords } = require("./query-paths");

const MISSING = "—";

const STATUS_FILTER_FIELDS = [
  { key: "prefix", title: "Prefix" },
  { key: "folder", title: "Folder" },
  { key: "status", title: "Status" },
  { key: "stage", title: "Stage" },
  { key: "class", title: "Class" },
];

const STATUS_SORT_MODES = [
  ["slug", "Slug"],
  ["filename", "Filename"],
  ["folder", "Folder"],
  ["prefix", "Prefix"],
  ["last_modified", "Last modified"],
];

function asStatusRow(app, record, { missing = MISSING } = {}) {
  return {
    ...record,
    prefix: record.prefix || missing,
    folder: record.folder || missing,
    class: getFrontmatterValue(app, record.file, "class", missing),
    stage: getFrontmatterValue(app, record.file, "stage", missing),
    status: getFrontmatterValue(app, record.file, "status", missing),
    modifiedAgo: formatRelativeTime(record.mtime),
  };
}

function pathSegments(vaultPath) {
  return String(vaultPath || "")
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function normalizeRoot(root) {
  return String(root || "_autoscribe").replace(/^\/+|\/+$/g, "");
}

function isInsideRoot(vaultPath, root) {
  const segments = pathSegments(vaultPath);
  return segments[0] === root;
}

function rootRelativeFolder(vaultPath, root, { rootLabel = MISSING } = {}) {
  const segments = pathSegments(vaultPath);

  if (segments[0] !== root) return rootLabel;

  const folderSegments = segments.slice(1, -1);
  if (folderSegments.length === 0) return rootLabel;

  return folderSegments.join("/");
}

function autoscribeSlugRecords(records, { root = "_autoscribe", rootLabel = MISSING } = {}) {
  const normalizedRoot = normalizeRoot(root);

  return records
    .filter((record) => isInsideRoot(record.path, normalizedRoot))
    .map((record) => ({
      ...record,
      folder: rootRelativeFolder(record.path, normalizedRoot, { rootLabel }),
    }));
}

function duplicateSlugSet(records) {
  const counts = new Map();

  for (const record of records) {
    if (!record?.slug) continue;
    counts.set(record.slug, (counts.get(record.slug) || 0) + 1);
  }

  const duplicates = new Set();

  for (const [slug, count] of counts.entries()) {
    if (count > 1) duplicates.add(slug);
  }

  return duplicates;
}

function scopedSlugIndex(slugIndex, records) {
  return {
    ...slugIndex,
    records,
    duplicateSlugs: duplicateSlugSet(records),
  };
}

function buildRowsFromRecords(app, slugIndex, records, { missing = MISSING } = {}) {
  const scopedIndex = scopedSlugIndex(slugIndex, records);
  const rows = records.map((record) => asStatusRow(app, record, { missing }));

  return {
    slugIndex: scopedIndex,
    rows,
  };
}

function buildPublicStatusRows(app, { prefixes = [], excludePaths = [], missing = MISSING } = {}) {
  const slugIndex = buildSlugIndex(app, {
    prefixes,
    excludePaths,
  });

  const records = publicSlugRecords(slugIndex.records, { rootLabel: missing });

  return buildRowsFromRecords(app, slugIndex, records, { missing });
}

function buildAutoscribeStatusRows(
  app,
  { prefixes = [], excludePaths = [], root = "_autoscribe", missing = MISSING } = {}
) {
  const slugIndex = buildSlugIndex(app, {
    prefixes,
    excludePaths,
  });

  const records = autoscribeSlugRecords(slugIndex.records, {
    root,
    rootLabel: missing,
  });

  return buildRowsFromRecords(app, slugIndex, records, { missing });
}

function localeCompare(a, b) {
  return String(a ?? "").localeCompare(String(b ?? ""), undefined, {
    sensitivity: "base",
  });
}

function sortStatusRows(filteredRows, sortMode) {
  const rows = [...filteredRows];

  if (sortMode === "last_modified") {
    rows.sort((a, b) => {
      const diff = (b.mtime ?? 0) - (a.mtime ?? 0);
      if (diff !== 0) return diff;
      return localeCompare(a.slug, b.slug);
    });
  } else if (sortMode === "filename") {
    rows.sort((a, b) => {
      const diff = localeCompare(a.name, b.name);
      if (diff !== 0) return diff;
      return localeCompare(a.slug, b.slug);
    });
  } else if (sortMode === "folder") {
    rows.sort((a, b) => {
      const diff = localeCompare(a.folder, b.folder);
      if (diff !== 0) return diff;
      return localeCompare(a.slug, b.slug);
    });
  } else if (sortMode === "prefix") {
    rows.sort((a, b) => {
      const diff = localeCompare(a.prefix, b.prefix);
      if (diff !== 0) return diff;
      return localeCompare(a.slug, b.slug);
    });
  } else {
    rows.sort((a, b) => localeCompare(a.slug, b.slug));
  }

  return rows;
}

function serializeStatusRow(row, index) {
  return {
    order: index + 1,
    slug: row.slug,
    path: row.path,
    name: row.name,
    basename: row.basename ?? row.name,
    prefix: row.prefix,
    folder: row.folder,
    class: row.class,
    stage: row.stage,
    status: row.status,
    mtime: row.mtime,
  };
}

function serializeInstructionRow(row) {
  if (!row) return null;

  return {
    slug: row.slug,
    path: row.path,
    name: row.name,
    basename: row.basename ?? row.name,
    prefix: row.prefix,
    folder: row.folder,
    class: row.class,
    stage: row.stage,
    status: row.status,
    mtime: row.mtime,
  };
}

function statusColumns() {
  return [
    {
      title: "Note",
      render(cell, row, ctx) {
        ctx.createInternalLink(cell, row.path, row.name);
      },
    },
    { title: "Slug", key: "slug" },
    { title: "Folder", key: "folder" },
    { title: "Prefix", key: "prefix" },
    { title: "Class", key: "class" },
    { title: "Stage", key: "stage" },
    { title: "Status", key: "status" },
    { title: "Modified", key: "modifiedAgo" },
  ];
}

function renderDuplicateSlugWarning(parent, duplicateSlugs) {
  if (!duplicateSlugs || duplicateSlugs.size === 0) return;

  const warning = parent.createDiv();
  warning.style.marginBottom = "0.75em";
  warning.style.color = "var(--text-warning)";
  warning.setText(
    `${duplicateSlugs.size} duplicate slug(s) detected. Check the Slug column before processing.`
  );
}

function isAllowedContentPrefix(prefix, { instructionPrefix = "spc", slugPrefixes = [] } = {}) {
  if (prefix === instructionPrefix) return false;
  if (!Array.isArray(slugPrefixes) || slugPrefixes.length === 0) return true;
  return slugPrefixes.includes(prefix);
}

module.exports = {
  MISSING,
  STATUS_FILTER_FIELDS,
  STATUS_SORT_MODES,
  asStatusRow,
  buildPublicStatusRows,
  buildAutoscribeStatusRows,
  sortStatusRows,
  serializeStatusRow,
  serializeInstructionRow,
  statusColumns,
  renderDuplicateSlugWarning,
  isAllowedContentPrefix,

  // Exported mainly for testing/debugging.
  autoscribeSlugRecords,
  duplicateSlugSet,
};