"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { loadConfig } = require("../lib/config-loader.js");
const { requireVaultBasePath } = require("../lib/vault-paths.js");
function protocolConfig() { return loadConfig("protocol").current_selection || {}; }
function pathsConfig() { return loadConfig("paths"); }

const vaultRoot = requireVaultBasePath;

function sessionToken() {
  if (typeof process !== "undefined" && process?.pid) return `pid-${process.pid}`;
  return "browser-session";
}

function vaultKey(app) {
  const root = vaultRoot(app);
  const name = path.basename(root).toLowerCase().replace(/[^a-z0-9._-]+/g, "-") || "vault";
  const digest = crypto.createHash("sha256").update(root).digest("hex").slice(0, 12);
  return `${name}-${digest}`;
}

function currentSelectionPath(app) {
  return path.join(os.tmpdir(), ...String(pathsConfig().current_selection_tmp || "autoscribe/obsidian/current-selection").split("/"), `${vaultKey(app)}.json`);
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

  for (const key of (protocolConfig().source_array_keys || [])) {
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

function buildCurrentSelection(app, { items, source = {}, action = protocolConfig().default_action } = {}) {
  const timestamp = new Date().toISOString();
  const normalized = normalizeItems(items);
  return {
    type: String(protocolConfig().type || "current_selection"),
    recordType: String(protocolConfig().record_type || "current_selection"),
    version: Number(protocolConfig().version || 1),
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
  const registryName = String(protocolConfig().browser_registry || "__autoscribeCurrentSelections");
  window[registryName] ||= Object.create(null);
  window[registryName][vaultKey(app)] = selection;
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
    ? window[String(protocolConfig().browser_registry || "__autoscribeCurrentSelections")]?.[key]
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

  if (selection?.type !== String(protocolConfig().type || "current_selection")) return null;
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
  if (typeof window !== "undefined") {
    const registryName = String(protocolConfig().browser_registry || "__autoscribeCurrentSelections");
    if (window[registryName]) delete window[registryName][vaultKey(app)];
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
