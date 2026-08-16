"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");

function vaultRoot(app) {
  const root = app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Current selection requires a filesystem-backed vault.");
  return path.resolve(root);
}

function sessionToken() {
  if (!process?.pid) throw new Error("Obsidian Desktop process id is unavailable.");
  return `pid-${process.pid}`;
}

function vaultKey(app) {
  const root = vaultRoot(app);
  const name = path.basename(root).toLowerCase().replace(/[^a-z0-9._-]+/g, "-") || "vault";
  const digest = crypto.createHash("sha256").update(root).digest("hex").slice(0, 12);
  return `${name}-${digest}`;
}

function currentSelectionPath(app) {
  return path.join(os.tmpdir(), "autoscribe", "obsidian", "current-selection", `${vaultKey(app)}.json`);
}

function normalizeItem(item, index) {
  if (!item || typeof item !== "object") return null;
  const pathValue = String(item.path || item.file || item.filepath || item.vault_path || "").trim();
  const slug = String(item.slug || item.uid || "").trim();
  if (!pathValue && !slug) return null;
  return {
    order: Number(item.order || item.index) || index + 1,
    path: pathValue,
    slug,
    title: String(item.title || item.label || item.name || "").trim(),
    ...item,
    path: pathValue,
    slug,
  };
}

function sourceItems(selection) {
  if (Array.isArray(selection)) return selection;
  if (!selection || typeof selection !== "object") return [];
  if (Array.isArray(selection.items)) return selection.items;

  const paths = Array.isArray(selection.paths) ? selection.paths : [];
  const slugs = Array.isArray(selection.slugs) ? selection.slugs : [];
  const count = Math.max(paths.length, slugs.length);
  if (count) {
    return Array.from({ length: count }, (_unused, index) => ({
      path: paths[index] || "",
      slug: slugs[index] || "",
    }));
  }

  for (const key of ["records", "selected", "files", "prompts"]) {
    if (Array.isArray(selection[key])) return selection[key];
  }
  return [];
}

function normalizeItems(items) {
  const seen = new Set();
  const output = [];
  for (const item of sourceItems(items)) {
    const normalized = normalizeItem(item, output.length);
    if (!normalized) continue;
    const identity = normalized.path ? `path:${normalized.path}` : `slug:${normalized.slug}`;
    if (seen.has(identity)) continue;
    seen.add(identity);
    normalized.order = output.length + 1;
    output.push(normalized);
  }
  return output;
}

function buildCurrentSelection(app, { items, source = {}, action = "save" } = {}) {
  const timestamp = new Date().toISOString();
  const normalized = normalizeItems(items);
  return {
    type: "current_selection",
    recordType: "current_selection",
    version: 1,
    session_token: sessionToken(),
    vault_key: vaultKey(app),
    vault_root: vaultRoot(app),
    updated_at: timestamp,
    action,
    source: {
      namespace: source.namespace || "",
      query_path: source.queryPath || source.query_path || "",
      title: source.title || "",
    },
    count: normalized.length,
    paths: normalized.map(item => item.path).filter(Boolean),
    slugs: normalized.map(item => item.slug).filter(Boolean),
    items: normalized,
  };
}

function publish(app, selection) {
  if (typeof window === "undefined") return;
  window.__autoscribeCurrentSelections ||= Object.create(null);
  window.__autoscribeCurrentSelections[vaultKey(app)] = selection;
}

function writeCurrentSelection(app, params) {
  const selection = buildCurrentSelection(app, params);
  const file = currentSelectionPath(app);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process?.pid || "tmp"}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(selection, null, 2)}\n`, "utf8");
  fs.renameSync(temp, file);
  publish(app, selection);
  return { file, selection };
}

function readCurrentSelection(app) {
  const key = vaultKey(app);
  const live = typeof window !== "undefined"
    ? window.__autoscribeCurrentSelections?.[key]
    : null;
  if (live?.session_token === sessionToken()) {
    live.items = normalizeItems(live);
    live.count = live.items.length;
    live.paths = live.items.map(item => item.path).filter(Boolean);
    live.slugs = live.items.map(item => item.slug).filter(Boolean);
    return live;
  }

  const file = currentSelectionPath(app);
  let selection;
  try {
    selection = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }

  if (selection?.type !== "current_selection") return null;
  if (selection?.vault_key !== key) return null;
  if (selection?.session_token !== sessionToken()) return null;
  selection.items = normalizeItems(selection);
  selection.count = selection.items.length;
  selection.paths = selection.items.map(item => item.path).filter(Boolean);
  selection.slugs = selection.items.map(item => item.slug).filter(Boolean);
  publish(app, selection);
  return selection;
}

function clearCurrentSelection(app) {
  const file = currentSelectionPath(app);
  fs.rmSync(file, { force: true });
  if (typeof window !== "undefined" && window.__autoscribeCurrentSelections) {
    delete window.__autoscribeCurrentSelections[vaultKey(app)];
  }
}

module.exports = {
  buildCurrentSelection,
  clearCurrentSelection,
  currentSelectionPath,
  readCurrentSelection,
  sourceItems,
  sessionToken,
  vaultKey,
  writeCurrentSelection,
};
