# Dispatch Run

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const path = require("path");

const TRANSCLUSION_RE = /!\[\[([^\]]+)\]\]/g;

function clipboardCandidates(text) {
  const rows = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!rows.length) return [];

  const firstCells = rows[0].split("\t").map((cell) => cell.trim().toLowerCase());
  const fileNameIndex = firstCells.findIndex((cell) => cell === "file name" || cell === "filename" || cell === "file");
  const pathIndex = firstCells.findIndex((cell) => cell === "path" || cell === "filepath" || cell === "file path");
  const hasHeader = fileNameIndex >= 0 || pathIndex >= 0;
  const candidates = [];

  for (let index = hasHeader ? 1 : 0; index < rows.length; index += 1) {
    const row = rows[index];
    const cells = row.split("\t").map((cell) => cell.trim());
    let candidate = "";

    if (pathIndex >= 0) candidate = cells[pathIndex] || "";
    if (!candidate && fileNameIndex >= 0) candidate = cells[fileNameIndex] || "";
    if (!candidate) candidate = cells.find((cell) => /\.md$/i.test(cell)) || "";

    if (!candidate) {
      const wiki = row.match(/\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/);
      if (wiki) candidate = wiki[1].trim();
    }

    if (candidate) candidates.push(candidate);
  }

  return candidates;
}

function normalizeCandidate(value) {
  return String(value || "")
    .trim()
    .replace(/^file:\/\//, "")
    .replace(/^\[\[/, "")
    .replace(/\]\]$/, "")
    .split("|")[0]
    .trim()
    .replace(/\\/g, "/");
}

function resolveSelection(app, text) {
  const paths = [];
  const seen = new Set();

  for (const raw of clipboardCandidates(text)) {
    const candidate = normalizeCandidate(raw);
    if (!candidate) continue;

    let file = app.vault.getAbstractFileByPath(candidate);
    if (!file && !/\.md$/i.test(candidate)) {
      file = app.vault.getAbstractFileByPath(`${candidate}.md`);
    }
    if (!file) {
      file = app.metadataCache.getFirstLinkpathDest(candidate.replace(/\.md$/i, ""), "");
    }
    if (!file || file.extension !== "md") {
      throw new Error(`Could not resolve selected Markdown file: ${raw}`);
    }
    if (!seen.has(file.path)) {
      seen.add(file.path);
      paths.push(file.path);
    }
  }

  return paths;
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
  const { createDispatchBranch } = require(path.join(vaultRoot, "_control/scripts/lib/git-transport.js"));
  const { listPlanRecords, loadPlanRecord } = require(path.join(vaultRoot, "_control/scripts/plans/plan-store.js"));

  const heading = container.createEl("h2", { text: "Dispatch selected files" });
  heading.style.marginTop = "0";
  const selectionRow = container.createEl("div");
  selectionRow.style.display = "flex";
  selectionRow.style.gap = "0.75em";
  selectionRow.style.alignItems = "center";
  selectionRow.style.marginBottom = "0.75em";

  const status = selectionRow.createEl("div", { text: "Loading selection…" });
  const reloadButton = selectionRow.createEl("button", { text: "Reload Clipboard" });
  const list = container.createEl("ul");
  list.style.marginTop = "0";

  let selection = [];
  async function loadClipboardSelection() {
    reloadButton.disabled = true;
    status.setText("Loading clipboard selection…");
    list.empty();
    try {
      selection = resolveSelection(app, await navigator.clipboard.readText());
      if (!selection.length) {
        status.setText("The clipboard selection contains no resolvable Markdown files.");
        return;
      }
      status.setText(`${selection.length} selected file${selection.length === 1 ? "" : "s"}`);
      for (const selectedPath of selection) list.createEl("li", { text: selectedPath });
    } catch (error) {
      selection = [];
      status.setText(`Could not load clipboard selection: ${error.message || error}`);
    } finally {
      reloadButton.disabled = false;
    }
  }

  reloadButton.addEventListener("click", loadClipboardSelection);
  await loadClipboardSelection();

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
      if (!selection.length) {
        throw new Error("Reload the clipboard with at least one resolvable Markdown file.");
      }
      const flattened = await flattenInPlace(app, selection);
      const basename = combineBasename.value.trim();
      if (combine.checked && !basename) {
        throw new Error("Enter a basename for the combined record.");
      }
      const transport = createDispatchBranch(app, {
        paths: selection,
        planRecord: loadPlanRecord(app, select.value),
        message: message.value.trim(),
        combineBasename: combine.checked ? basename : ""
      });
      result.setText(
        `Transport branch created.
` +
        `Branch: ${transport.branch}
` +
        `Run: ${transport.run_identity}
` +
        `Records: ${transport.count}
` +
        `Flattened in place: ${flattened.length}
` +
        `The feeder can now claim this branch.`
      );
    } catch (error) {
      result.setText(`Dispatch failed: ${error.message || error}`);
    } finally {
      runButton.disabled = false;
    }
  });
}

await renderDispatchRun({ app, dv, container: dv.container });
````
