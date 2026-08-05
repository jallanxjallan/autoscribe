"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const runtimeApp = globalThis.app;
const controlVaultRoot = runtimeApp.vault.adapter.getBasePath?.() || runtimeApp.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const path = require("path");

const TRANSCLUSION_RE = /!\[\[([^\]]+)\]\]/g;

const SESSION_KEY = "__autoscribeDispatchRunSessions";

function sessionRegistry() {
  if (!globalThis[SESSION_KEY]) globalThis[SESSION_KEY] = new Map();
  return globalThis[SESSION_KEY];
}

function vaultSessionKey(app) {
  return app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath || app.vault.getName();
}

function getDispatchSession(app) {
  const registry = sessionRegistry();
  const key = vaultSessionKey(app);
  let session = registry.get(key);
  if (!session) {
    session = { candidates: new Map(), cleanupRegistered: false };
    registry.set(key, session);
  }
  if (!session.cleanupRegistered) {
    const clear = () => registry.delete(key);
    session.cleanupRegistered = true;
    try { app.workspace.on("quit", clear); } catch (_) {}
    try { window.addEventListener("beforeunload", clear, { once: true }); } catch (_) {}
  }
  return session;
}

function normalizeCandidate(value) {
  return String(value || "")
    .trim()
    .replace(/^file:\/\//i, "")
    .replace(/^!\[\[/, "[[")
    .replace(/^\[\[/, "")
    .replace(/\]\]$/, "")
    .split("|")[0]
    .split("#")[0]
    .trim()
    .replace(/\\/g, "/");
}

function clipboardCandidates(text) {
  const results = [];
  for (const line of String(text || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const wikilinks = [...trimmed.matchAll(/!?\[\[([^\]]+)\]\]/g)];
    if (wikilinks.length) {
      for (const match of wikilinks) results.push(match[1]);
      continue;
    }

    for (const cell of trimmed.split("\t")) {
      const value = normalizeCandidate(cell);
      if (!value) continue;
      if (/^(file ?name|filename|file|path|filepath|file path|slug|title)$/i.test(value)) continue;
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
    const matches = app.vault.getMarkdownFiles().filter((item) => {
      const cache = app.metadataCache.getFileCache(item);
      return String(cache?.frontmatter?.slug || "").trim() === candidate;
    });
    if (matches.length === 1) file = matches[0];
  }

  return file?.extension === "md" ? file : null;
}

function appendClipboardCandidates(app, session, text) {
  let added = 0;
  for (const raw of clipboardCandidates(text)) {
    const file = resolveCandidate(app, raw);
    if (!file || session.candidates.has(file.path)) continue;
    session.candidates.set(file.path, { path: file.path, title: file.basename, selected: true });
    added += 1;
  }
  return added;
}

function splitFrontmatter(text) {
  const match = String(text).match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n?)([\s\S]*)$/);
  return match ? { frontmatter: match[1], body: match[2] } : { frontmatter: "", body: String(text) };
}

function parseTransclusion(rawTarget) {
  const target = String(rawTarget || "").split("|")[0].trim();
  const hashAt = target.indexOf("#");
  return hashAt < 0
    ? { linkpath: target, fragment: "" }
    : { linkpath: target.slice(0, hashAt).trim(), fragment: target.slice(hashAt + 1).trim() };
}

function extractHeadingSection(body, heading) {
  const wanted = heading.trim().toLowerCase();
  const lines = body.split(/\r?\n/);
  let start = -1;
  let level = 0;

  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (match && match[2].trim().toLowerCase() === wanted) {
      start = index;
      level = match[1].length;
      break;
    }
  }
  if (start < 0) throw new Error(`Transcluded heading not found: ${heading}`);

  let end = lines.length;
  for (let index = start + 1; index < lines.length; index += 1) {
    const match = lines[index].match(/^(#{1,6})\s+/);
    if (match && match[1].length <= level) {
      end = index;
      break;
    }
  }
  return lines.slice(start, end).join("\n");
}

function extractBlock(body, blockId) {
  const escaped = String(blockId).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const marker = new RegExp(`\\s*\\^${escaped}\\s*$`);
  const lines = body.split(/\r?\n/);
  const index = lines.findIndex((line) => marker.test(line));
  if (index < 0) throw new Error(`Transcluded block not found: ^${blockId}`);

  let start = index;
  while (start > 0 && lines[start - 1].trim() !== "") start -= 1;
  let end = index + 1;
  while (end < lines.length && lines[end].trim() !== "") end += 1;

  const selected = lines.slice(start, end);
  selected[selected.length - 1] = selected[selected.length - 1].replace(marker, "");
  return selected.join("\n").trimEnd();
}

function selectFragment(body, fragment) {
  if (!fragment) return body;
  if (fragment.startsWith("^")) return extractBlock(body, fragment.slice(1));
  return extractHeadingSection(body, fragment);
}

async function resolveBodyTransclusions(app, body, sourcePath, stack = []) {
  const matches = [...String(body).matchAll(TRANSCLUSION_RE)];
  if (!matches.length) return { body: String(body), wikilinks: [] };

  let output = "";
  let cursor = 0;
  const wikilinks = [];
  const seenLinks = new Set();

  function remember(link) {
    if (!seenLinks.has(link)) {
      seenLinks.add(link);
      wikilinks.push(link);
    }
  }

  for (const match of matches) {
    output += body.slice(cursor, match.index);
    cursor = match.index + match[0].length;

    const rawTarget = String(match[1] || "").trim();
    remember(`[[${rawTarget}]]`);
    const { linkpath, fragment } = parseTransclusion(rawTarget);
    const target = app.metadataCache.getFirstLinkpathDest(linkpath, sourcePath);
    if (!target) throw new Error(`Could not resolve transclusion ${match[0]} in ${sourcePath}`);
    if (target.extension !== "md") throw new Error(`Transclusion is not Markdown: ${match[0]} in ${sourcePath}`);
    if (stack.includes(target.path)) {
      throw new Error(`Circular transclusion detected: ${[...stack, target.path].join(" -> ")}`);
    }

    const embedded = splitFrontmatter(await app.vault.read(target)).body;
    const selected = selectFragment(embedded, fragment);
    const nested = await resolveBodyTransclusions(app, selected, target.path, [...stack, target.path]);
    output += nested.body;
    for (const link of nested.wikilinks) remember(link);
  }
  return { body: output + body.slice(cursor), wikilinks };
}

async function flattenInPlace(app, selectedPaths) {
  const changed = [];
  for (const selectedPath of selectedPaths) {
    const file = app.vault.getAbstractFileByPath(selectedPath);
    if (!file || file.extension !== "md") throw new Error(`Selected Markdown file was not found: ${selectedPath}`);

    const original = await app.vault.read(file);
    const { frontmatter, body } = splitFrontmatter(original);
    const matches = [...String(body).matchAll(TRANSCLUSION_RE)];
    if (!matches.length) continue;

    const resolved = await resolveBodyTransclusions(app, body, file.path, [file.path]);
    const flattened = frontmatter + resolved.body;
    if (flattened !== original) await app.vault.modify(file, flattened);
    await app.fileManager.processFrontMatter(file, (properties) => {
      properties.transclusions = resolved.wikilinks;
    });
    changed.push(file.path);
  }
  return changed;
}

async function renderDispatchRun({ app, container }) {
  container.empty();
  const vaultRoot = app.vault.adapter.basePath;
  const { createDispatchBranch, clearPipelineMetadata } = require(path.join(vaultRoot, "_control/scripts/lib/git-transport.js"));
  const { listPlanRecords, loadPlanRecord } = require(path.join(vaultRoot, "_control/scripts/plans/plan-store.js"));
  const { runFeederCommand } = require(path.join(vaultRoot, "_control/scripts/lib/feeder-command.js"));

  const session = getDispatchSession(app);
  const heading = container.createEl("h2", { text: "Dispatch candidate files" });
  heading.style.marginTop = "0";

  const selectionRow = container.createEl("div");
  selectionRow.style.display = "flex";
  selectionRow.style.gap = "0.5em";
  selectionRow.style.alignItems = "center";
  selectionRow.style.flexWrap = "wrap";
  selectionRow.style.marginBottom = "0.75em";

  const status = selectionRow.createEl("div", { text: "Loading candidates…" });
  status.style.marginRight = "auto";
  const clearButton = selectionRow.createEl("button", { text: "Clear Dispatch List" });
  const selectAllButton = selectionRow.createEl("button", { text: "Select all" });
  const selectNoneButton = selectionRow.createEl("button", { text: "Select none" });
  const list = container.createEl("div");
  list.style.display = "grid";
  list.style.gap = "0.35em";
  list.style.marginBottom = "1em";

  function selectedPaths() {
    return [...session.candidates.values()].filter((item) => item.selected).map((item) => item.path);
  }

  function renderCandidates(note = "") {
    list.empty();
    const candidates = [...session.candidates.values()];
    const selectedCount = candidates.filter((item) => item.selected).length;
    status.setText(
      candidates.length
        ? `${candidates.length} candidate${candidates.length === 1 ? "" : "s"}; ${selectedCount} selected${note ? ` — ${note}` : ""}`
        : `No candidate files in this vault session${note ? ` — ${note}` : ""}`
    );
    for (const item of candidates) {
      const row = list.createEl("label");
      row.style.display = "flex";
      row.style.gap = "0.55em";
      row.style.alignItems = "baseline";
      const checkbox = row.createEl("input", { attr: { type: "checkbox" } });
      checkbox.checked = item.selected;
      checkbox.addEventListener("change", () => {
        item.selected = checkbox.checked;
        renderCandidates();
      });
      const text = row.createSpan();
      text.createEl("strong", { text: item.title });
      text.createSpan({ text: ` — ${item.path}` });
    }
  }

  async function addClipboardSelection() {
    try {
      const added = appendClipboardCandidates(app, session, await navigator.clipboard.readText());
      renderCandidates(added ? `added ${added} from clipboard` : "clipboard contained no new file references");
    } catch (error) {
      renderCandidates(`could not read clipboard: ${error.message || error}`);
    }
  }

  clearButton.addEventListener("click", () => {
    session.candidates.clear();
    renderCandidates("dispatch list cleared");
  });
  selectAllButton.addEventListener("click", () => {
    for (const item of session.candidates.values()) item.selected = true;
    renderCandidates();
  });
  selectNoneButton.addEventListener("click", () => {
    for (const item of session.candidates.values()) item.selected = false;
    renderCandidates();
  });

  await addClipboardSelection();

  const planRows = listPlanRecords(app);
  if (!Array.isArray(planRows) || !planRows.length) {
    container.createEl("p", { text: "No plans are available." });
    return;
  }

  const form = container.createEl("div");
  form.style.display = "grid";
  form.style.gap = "0.6em";
  form.style.maxWidth = "42em";
  form.createEl("label", { text: "Plan" });
  const select = form.createEl("select");
  for (const plan of planRows) {
    const slug = String(plan.record_identity || plan.slug || "").trim();
    if (!slug) continue;
    select.createEl("option", { text: String(plan.payload?.label || plan.label || plan.name || slug), value: slug });
  }

  form.createEl("label", { text: "Commit message (optional)" });
  const message = form.createEl("input", { attr: { type: "text", placeholder: "Defaults to DISPATCH <plan>: <timestamp>" } });

  const combineRow = form.createEl("label");
  combineRow.style.display = "flex";
  combineRow.style.gap = "0.5em";
  combineRow.style.alignItems = "center";
  const combine = combineRow.createEl("input", { attr: { type: "checkbox" } });
  combineRow.createSpan({ text: "Combine selected files" });

  form.createEl("label", { text: "Combined record basename" });
  const combineBasename = form.createEl("input", {
    attr: { type: "text", placeholder: "Example: chapter-one", disabled: "disabled" }
  });
  combine.addEventListener("change", () => {
    combineBasename.disabled = !combine.checked;
    if (combine.checked) combineBasename.focus();
  });

  const runButton = form.createEl("button", { text: "Dispatch Run", cls: "mod-cta" });
  const result = container.createEl("pre");
  result.style.whiteSpace = "pre-wrap";

  runButton.addEventListener("click", async () => {
    runButton.disabled = true;
    result.setText("Resolving transclusions and creating transport branch…");
    try {
      const selection = selectedPaths();
      if (!selection.length) {
        throw new Error("Select at least one candidate file.");
      }
      const flattened = await flattenInPlace(app, selection);
      const basename = combineBasename.value.trim();
      if (combine.checked && !basename) {
        throw new Error("Enter a basename for the combined record.");
      }
      clearPipelineMetadata(app, selection);
      const transport = createDispatchBranch(app, {
        paths: selection,
        planRecord: loadPlanRecord(app, select.value),
        message: message.value.trim(),
        combineBasename: combine.checked ? basename : ""
      });
      const feeder = await runFeederCommand(app, ["dispatch-run", "--branch", transport.branch], { detached: true });
      session.candidates.clear();
      renderCandidates("manifest cleared after dispatch");
      result.setText(
        `Transport branch created and handed to feeder.
` +
        `Branch: ${transport.branch}
` +
        `Run: ${transport.run_identity}
` +
        `Records: ${transport.count}
` +
        `Flattened in place: ${flattened.length}
` +
        `Feeder PID: ${feeder.pid}
` +
        `Use obs log from this vault to inspect the handoff.`
      );
    } catch (error) {
      result.setText(`Dispatch failed: ${error.message || error}`);
    } finally {
      runButton.disabled = false;
    }
  });
}


module.exports = { renderDispatchRun };
