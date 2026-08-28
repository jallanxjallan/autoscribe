"use strict";

function createControlRuntime(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!base) throw new Error("Could not determine vault base path.");
  const loaderPath = path.join(base, "_control", "scripts", "lib", "control-loader.js");
  try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
  const { createControlLoader } = nodeRequire(loaderPath);
  return createControlLoader({ app, controlRoot: "_control" });
}

function identity(record) {
  return String(record?.record_identity || record?.slug || record?.key || "").trim();
}

function label(record) {
  return String(record?.payload?.label || record?.label || record?.title || record?.name || identity(record)).trim();
}

function normalizeClipboardRef(value) {
  let ref = String(value || "").trim();
  if (!ref) return "";

  if (ref.startsWith("[[") && ref.endsWith("]]")) {
    ref = ref.slice(2, -2).trim();
  }

  ref = ref.split("|")[0].trim();
  ref = ref.split("#")[0].trim();
  ref = ref.split("^")[0].trim();
  return ref.replace(/^\.\//, "");
}

function clipboardRefs(text) {
  const source = String(text || "").replace(/\r\n?/g, "\n");
  if (!source.trim()) return [];

  const refs = [];
  const wikilinks = /\[\[([^\]]+)\]\]/g;
  let match;
  while ((match = wikilinks.exec(source)) !== null) {
    const ref = normalizeClipboardRef(match[1]);
    if (ref) refs.push(ref);
  }

  const remainder = source.replace(wikilinks, "\n");
  for (const row of remainder.split("\n")) {
    for (const cell of row.split("\t")) {
      const ref = normalizeClipboardRef(cell);
      if (ref) refs.push(ref);
    }
  }

  return refs;
}

function buildSlugIndex(app) {
  const index = new Map();
  const duplicates = new Set();

  for (const file of app.vault.getMarkdownFiles()) {
    const slug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
    if (!slug) continue;
    if (index.has(slug)) duplicates.add(slug);
    else index.set(slug, file);
  }

  return { index, duplicates };
}

function resolveClipboardRef(app, rawRef, slugIndex, duplicateSlugs) {
  const ref = normalizeClipboardRef(rawRef);
  if (!ref) return null;

  const exact = app.vault.getAbstractFileByPath(ref);
  if (exact?.extension === "md") return exact;

  if (!ref.toLowerCase().endsWith(".md")) {
    const withExtension = app.vault.getAbstractFileByPath(`${ref}.md`);
    if (withExtension?.extension === "md") return withExtension;
  }

  if (duplicateSlugs.has(ref)) {
    throw new Error(`Clipboard slug is duplicated in the vault: ${ref}`);
  }
  const bySlug = slugIndex.get(ref);
  if (bySlug) return bySlug;

  const linked = app.metadataCache.getFirstLinkpathDest(ref, "");
  if (linked?.extension === "md") return linked;

  return null;
}

async function clipboardDocuments(app) {
  const readText = globalThis.navigator?.clipboard?.readText;
  if (typeof readText !== "function") return [];

  let text;
  try {
    text = await readText.call(globalThis.navigator.clipboard);
  } catch (_) {
    return [];
  }

  const refs = clipboardRefs(text);
  if (!refs.length) return [];

  const { index, duplicates } = buildSlugIndex(app);
  const documents = [];
  const seenPaths = new Set();
  const seenSlugs = new Set();

  for (const rawRef of refs) {
    const file = resolveClipboardRef(app, rawRef, index, duplicates);
    if (!file) continue;

    const slug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
    if (!slug) {
      throw new Error(`Clipboard file is missing required slug property: ${file.path}`);
    }
    if (seenPaths.has(file.path) || seenSlugs.has(slug)) continue;

    seenPaths.add(file.path);
    seenSlugs.add(slug);
    documents.push({
      path: file.path,
      slug,
      title: file.basename || slug,
      source: "clipboard",
    });
  }

  return documents;
}

function mergeDocuments(primary, secondary) {
  const output = [];
  const seenPaths = new Set();
  const seenSlugs = new Set();

  for (const document of [...primary, ...secondary]) {
    if (!document?.path || !document?.slug) continue;
    if (seenPaths.has(document.path) || seenSlugs.has(document.slug)) continue;
    seenPaths.add(document.path);
    seenSlugs.add(document.slug);
    output.push(document);
  }

  return output;
}

function sortedPlans(state, catalogsFromState) {
  return catalogsFromState(state).plans
    .filter((record) => identity(record))
    .sort((a, b) =>
      (Number(b?.usage_score || 0) - Number(a?.usage_score || 0)) ||
      label(a).localeCompare(label(b), undefined, { sensitivity: "base", numeric: true }) ||
      identity(a).localeCompare(identity(b), undefined, { sensitivity: "base", numeric: true })
    );
}

function selectionDocuments(app, selection) {
  const items = Array.isArray(selection?.items) ? selection.items : [];
  const documents = [];
  const seenSlugs = new Set();
  const seenPaths = new Set();

  for (const item of items) {
    const itemPath = String(item?.path || "").trim();
    if (!itemPath) throw new Error("Current selection contains an item without a filepath. Refresh the source query and try again.");

    const file = app.vault.getAbstractFileByPath(itemPath);
    if (!file || file.extension !== "md") throw new Error(`Selected Markdown file was not found: ${itemPath}`);

    const liveSlug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
    if (!liveSlug) throw new Error(`Selected file is missing required slug property: ${itemPath}`);

    const selectedSlug = String(item?.slug || "").trim();
    if (selectedSlug && selectedSlug !== liveSlug) {
      throw new Error(`Selection is stale for ${itemPath}: selected slug '${selectedSlug}' but file now has '${liveSlug}'.`);
    }
    if (seenSlugs.has(liveSlug)) throw new Error(`Selected document slug is duplicated: ${liveSlug}`);
    if (seenPaths.has(file.path)) throw new Error(`Selected filepath is duplicated: ${file.path}`);

    seenSlugs.add(liveSlug);
    seenPaths.add(file.path);
    documents.push({
      path: file.path,
      slug: liveSlug,
      title: String(item?.title || file.basename || liveSlug),
      source: "current-selection",
    });
  }

  return documents;
}

function renderDocuments(container, documents) {
  container.empty();
  container.createEl("h3", { text: "Files selected for dispatch" });

  if (!documents.length) {
    container.createEl("p", { text: "No dispatchable file references found in the clipboard or current selection." });
    return;
  }

  const table = container.createEl("table");
  table.style.width = "100%";
  const head = table.createEl("tr");
  for (const heading of ["#", "File", "Slug", "Source"]) head.createEl("th", { text: heading });

  documents.forEach((document, index) => {
    const row = table.createEl("tr");
    row.createEl("td", { text: String(index + 1) });
    row.createEl("td", { text: document.path });
    row.createEl("td", { text: document.slug });
    row.createEl("td", { text: document.source === "clipboard" ? "Clipboard" : "Current selection" });
  });
}

module.exports = async function dispatch_run(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");

  const loader = createControlRuntime(app);
  const { openWorkflowModal } = loader.requireControl("scripts/lib/workflow-modal.js");
  const { notify } = loader.requireControl("scripts/lib/notify.js");
  const { readCurrentSelection, clearCurrentSelection } = loader.requireControl("scripts/selections/current-selection.js");
  const { readControlState, catalogsFromState } = loader.requireControl("scripts/lib/control-state.js");
  const { createDispatchCommit } = loader.requireControl("scripts/lib/git-dispatch.js");

  async function render(container) {
    container.empty();
    const heading = container.createEl("h2", { text: "Dispatch Run" });
    heading.style.marginTop = "0";
    container.createEl("p", {
      text: "Reads file references from the clipboard and current selection, then creates one narrowly scoped AutoScribe dispatch commit. Nothing is uploaded or enqueued here; the dispatch watcher will consume the commit asynchronously.",
    });

    const status = container.createEl("pre", { text: "Loading local selection and plan catalogue…" });
    status.style.whiteSpace = "pre-wrap";

    let state;
    let plans;
    let selection;
    let documents;
    try {
      const [clipboard, stateResult, selectionResult] = await Promise.all([
        clipboardDocuments(app),
        readControlState(app),
        Promise.resolve(readCurrentSelection(app)),
      ]);
      state = stateResult;
      selection = selectionResult;
      plans = sortedPlans(state, catalogsFromState);
      documents = mergeDocuments(
        clipboard,
        selectionDocuments(app, selection)
      );
    } catch (error) {
      status.setText(error?.message || String(error));
      throw error;
    }

    status.remove();

    const planRow = container.createEl("div");
    planRow.style.cssText = "display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.5rem 0 1rem";
    planRow.createSpan({ text: "Plan" });
    const planSelect = planRow.createEl("select");
    planSelect.style.minWidth = "min(36rem, 80vw)";

    if (!plans.length) {
      planSelect.createEl("option", { text: "No plans in local catalogue", value: "" });
      planSelect.disabled = true;
    } else {
      for (const plan of plans) {
        const slug = identity(plan);
        planSelect.createEl("option", { value: slug, text: `${label(plan)} — ${slug}` });
      }
    }

    const filesBox = container.createEl("div");
    renderDocuments(filesBox, documents);

    const actions = container.createEl("div");
    actions.style.cssText = "display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin-top:1rem";
    const reloadButton = actions.createEl("button", { text: "Reload" });
    const dispatchButton = actions.createEl("button", { text: "Dispatch Run", cls: "mod-cta" });
    dispatchButton.disabled = !plans.length || !documents.length;
    const output = container.createEl("pre", { text: "" });
    output.style.whiteSpace = "pre-wrap";

    reloadButton.addEventListener("click", async () => {
      reloadButton.disabled = true;
      dispatchButton.disabled = true;
      try {
        await render(container);
      } catch (error) {
        notify(`Dispatch Run reload failed: ${error?.message || error}`, 10000);
      }
    });

    dispatchButton.addEventListener("click", async () => {
      dispatchButton.disabled = true;
      reloadButton.disabled = true;
      output.setText("Creating dispatch commit…");
      try {
        const planSlug = String(planSelect.value || "").trim();
        if (!planSlug) throw new Error("Select a plan.");
        if (!documents.length) throw new Error("Current selection contains no dispatchable files.");

        const receipt = await createDispatchCommit(app, { planSlug, documents });
        clearCurrentSelection(app);

        const noun = receipt.count === 1 ? "document" : "documents";
        output.setText([
          `Dispatch commit created: ${receipt.short_commit}`,
          `Branch: ${receipt.branch}`,
          `Plan: ${receipt.plan_slug}`,
          `${receipt.count} ${noun} queued for the dispatch watcher.`,
        ].join("\n"));
        notify(`Dispatch commit ${receipt.short_commit} created: ${receipt.count} ${noun} queued.`, 7000);

        // Prevent accidental duplicate dispatch from the same modal after the
        // session selection has been consumed.
        documents = [];
        renderDocuments(filesBox, documents);
      } catch (error) {
        const message = error?.message || String(error);
        output.setText(`Dispatch commit failed.\n${message}`);
        notify(`Dispatch Run failed: ${message}`, 10000);
        dispatchButton.disabled = !plans.length || !documents.length;
      } finally {
        reloadButton.disabled = false;
      }
    });
  }

  return openWorkflowModal({
    app,
    title: "Dispatch Run",
    render: (container) => render(container),
  });
};
