"use strict";

const SESSION_KEY = "__autoscribeDispatchRunSessions";

function registry() {
  if (!globalThis[SESSION_KEY]) globalThis[SESSION_KEY] = new Map();
  return globalThis[SESSION_KEY];
}

function vaultKey(app) {
  return app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath || app.vault.getName();
}

function getFileManifest(app) {
  const store = registry();
  const key = vaultKey(app);
  let manifest = store.get(key);
  if (!manifest) {
    manifest = { candidates: new Map(), cleanupRegistered: false };
    store.set(key, manifest);
  }
  if (!manifest.cleanupRegistered) {
    const clear = () => store.delete(key);
    manifest.cleanupRegistered = true;
    try { app.workspace.on("quit", clear); } catch (_) {}
    try { window.addEventListener("beforeunload", clear, { once: true }); } catch (_) {}
  }
  return manifest;
}

function normalizeCandidate(value) {
  return String(value || "").trim().replace(/^file:\/\//i, "")
    .replace(/^!\[\[/, "[[").replace(/^\[\[/, "").replace(/\]\]$/, "")
    .split("|")[0].split("#")[0].trim().replace(/\\/g, "/");
}

function clipboardCandidates(text) {
  const results = [];
  for (const line of String(text || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const links = [...trimmed.matchAll(/!?\[\[([^\]]+)\]\]/g)];
    if (links.length) { for (const match of links) results.push(match[1]); continue; }
    for (const cell of trimmed.split("\t")) {
      const value = normalizeCandidate(cell);
      if (!value || /^(file ?name|filename|file|path|filepath|file path|slug|title)$/i.test(value)) continue;
      results.push(value);
    }
  }
  return results;
}

function resolveCandidate(app, raw) {
  const candidate = normalizeCandidate(raw);
  if (!candidate) return null;
  let file = app.vault.getAbstractFileByPath(candidate);
  if (!file && !/\.md$/i.test(candidate)) file = app.vault.getAbstractFileByPath(`${candidate}.md`);
  if (!file) file = app.metadataCache.getFirstLinkpathDest(candidate.replace(/\.md$/i, ""), "");
  if (!file && candidate.includes(".")) {
    const matches = app.vault.getMarkdownFiles().filter((item) =>
      String(app.metadataCache.getFileCache(item)?.frontmatter?.slug || "").trim() === candidate);
    if (matches.length === 1) file = matches[0];
  }
  return file?.extension === "md" ? file : null;
}

function appendClipboardCandidates(app, manifest, text) {
  let added = 0;
  for (const raw of clipboardCandidates(text)) {
    const file = resolveCandidate(app, raw);
    if (!file || manifest.candidates.has(file.path)) continue;
    manifest.candidates.set(file.path, { path: file.path, title: file.basename, selected: true });
    added += 1;
  }
  return added;
}

module.exports = { getFileManifest, appendClipboardCandidates, resolveCandidate, normalizeCandidate };
