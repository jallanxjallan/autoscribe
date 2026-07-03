```dataviewjs
const CONFIG = {
  tocPath: "", // Optional override. Leave blank to auto-select a root Markdown file.
  tempRoot: "",
  debug: false,

  // Files whose slug starts with one of these prefixes are considered
  // indexable. TOC-linked files are still displayed in TOC order;
  // matching files not linked in the TOC are listed separately.
  slugPrefixes: ["cnt", "ins"],

  unicodeReference: [
    { symbol: "❦", code: "U+2766", meaning: "Motif or chapter emblem" },
    { symbol: "▣", code: "U+25A3", meaning: "Boxout" },
    { symbol: "◈", code: "U+25C8", meaning: "Case, deal, or feature note" },
    { symbol: "¶", code: "U+00B6", meaning: "Narrative paragraph" },
    { symbol: "▯", code: "U+25AF", meaning: "Single page" },
    { symbol: "▭", code: "U+25AD", meaning: "Double page" },
  ],

  defaultClass: "—",
  defaultStatus: "—",
  defaultStage: "—",

  excludePaths: [
    ".obsidian",
    ".trash",
    ".autoscribe",
  ],
};

const nodeRequire =
  typeof require === "function"
    ? require
    : window.require;

const pathMod = nodeRequire("path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPathForBootstrap = app.workspace.getActiveFile().path;
const markerIndexForBootstrap = queryPathForBootstrap.indexOf("/queries/");

if (markerIndexForBootstrap === -1) {
  throw new Error(`Query is not inside a queries folder: ${queryPathForBootstrap}`);
}

const controlRootForBootstrap = queryPathForBootstrap.slice(0, markerIndexForBootstrap);
const runtimePath = pathMod.join(
  vaultBasePath,
  ...controlRootForBootstrap.split("/").filter(Boolean),
  "scripts",
  "lib",
  "query-runtime.js"
);

const { createQueryRuntime } = nodeRequire(runtimePath);
const runtime = createQueryRuntime({ app, queryTitle: "Content Index query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { setTriState } = loader.requireControl("scripts/lib/dom.js");

function asText(value, fallback = "") {
  if (value == null) return fallback;
  if (Array.isArray(value)) return value.map(v => String(v)).join(", ");
  const text = String(value).trim();
  return text || fallback;
}

function normalizePath(path) {
  return String(path || "").replace(/^\/+/, "");
}

function isUnderscoreFolder(path) {
  return normalizePath(path)
    .split("/")
    .slice(0, -1)
    .some(part => part.startsWith("_"));
}

function isExcludedPath(path) {
  const clean = normalizePath(path);

  if (isUnderscoreFolder(clean)) return true;

  return CONFIG.excludePaths.some(prefix => {
    const cleanPrefix = normalizePath(prefix).replace(/\/+$/, "");
    return clean === cleanPrefix || clean.startsWith(`${cleanPrefix}/`);
  });
}

function titleForPage(page, fallback = "") {
  return (
    asText(page?.title) ||
    asText(fallback) ||
    asText(page?.file?.name) ||
    asText(page?.file?.path)
  );
}

function isVaultRootFile(file) {
  const cleanPath = normalizePath(file?.path);
  return cleanPath && !cleanPath.includes("/");
}

function filenameTokens(file) {
  return String(file?.basename || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

function tocPriorityScore(file) {
  const basename = String(file?.basename || "").toLowerCase();
  const tokens = filenameTokens(file);
  const joined = tokens.join(" ");

  let score = 0;

  if (/^table\s+of\s+contents?$/.test(joined)) score += 100;
  if (tokens.includes("toc")) score += 90;
  if (tokens.includes("table")) score += 70;
  if (tokens.includes("contents")) score += 60;
  if (tokens.includes("content")) score += 50;

  if (basename.includes("toc")) score += 30;
  if (basename.includes("table")) score += 20;
  if (basename.includes("contents")) score += 15;
  if (basename.includes("content")) score += 10;

  return score;
}

function getRootMarkdownCandidates() {
  return app.vault.getMarkdownFiles()
    .filter(file => isVaultRootFile(file))
    .filter(file => !isExcludedPath(file.path))
    .sort((a, b) => {
      const scoreDiff = tocPriorityScore(b) - tocPriorityScore(a);
      if (scoreDiff !== 0) return scoreDiff;

      return String(a.name).localeCompare(String(b.name));
    });
}

function getTocFile() {
  const configuredPath = asText(CONFIG.tocPath).trim();

  if (configuredPath) {
    const cleanTocPath = normalizePath(configuredPath);

    const configuredFile = app.vault.getMarkdownFiles().find(file =>
      normalizePath(file.path) === cleanTocPath ||
      file.name === cleanTocPath
    );

    if (configuredFile) return configuredFile;

    throw new Error(`Configured table/content file not found: ${CONFIG.tocPath}`);
  }

  const candidates = getRootMarkdownCandidates();

  if (!candidates.length) {
    throw new Error("No Markdown files found at the vault root.");
  }

  return candidates[0];
}

function extractWikiLinks(line) {
  const links = [];
  const regex = /\[\[([^\]]+)\]\]/g;

  let match;
  while ((match = regex.exec(String(line || ""))) !== null) {
    const raw = match[1];

    const target = raw
      .split("|")[0]
      .split("#")[0]
      .trim();

    if (target) links.push(target);
  }

  return links;
}

function resolveMarkdownFileFromWikiTarget(target, sourcePath) {
  const cleanTarget = String(target || "").replace(/\.md$/i, "").trim();
  if (!cleanTarget) return null;

  const linkDest = app.metadataCache.getFirstLinkpathDest(cleanTarget, sourcePath);
  if (linkDest) return linkDest;

  return app.vault.getMarkdownFiles().find(file =>
    file.basename === cleanTarget ||
    normalizePath(file.path) === normalizePath(`${cleanTarget}.md`)
  ) || null;
}

function pageForFile(file) {
  if (!file || isExcludedPath(file.path)) return null;
  return dv.page(file.path) || null;
}

function normalizeSlug(value) {
  return asText(value).toLowerCase().trim();
}

function slugPrefixForSlug(slug) {
  const cleanSlug = normalizeSlug(slug);
  if (!cleanSlug) return "—";

  const explicitPrefix = CONFIG.slugPrefixes.find(prefix => {
    const cleanPrefix = String(prefix || "").toLowerCase().trim();
    return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
  });

  if (explicitPrefix) return String(explicitPrefix).toLowerCase().trim();

  return cleanSlug.split(/[.\-_/]/)[0] || "—";
}

function slugMatchesCriteria(slug) {
  const cleanSlug = normalizeSlug(slug);
  if (!cleanSlug) return false;

  return CONFIG.slugPrefixes.some(prefix => {
    const cleanPrefix = String(prefix || "").toLowerCase().trim();
    return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
  });
}

function candidateMarkdownFiles() {
  return app.vault.getMarkdownFiles()
    .filter(file => !isExcludedPath(file.path))
    .sort((a, b) => String(a.path).localeCompare(String(b.path)));
}

function headingKey(parts) {
  return parts
    .filter(Boolean)
    .map(part => String(part).trim())
    .join(" / ");
}

function headingLabel(parts, fallback = "Contents") {
  const clean = parts.filter(Boolean);
  return clean.length ? clean[clean.length - 1] : fallback;
}

function rowFromPage(page, file, context) {
  const path = normalizePath(file.path);
  const slug = asText(page?.slug);
  const title = titleForPage(page, file.basename);
  const modifiedMillis = page?.file?.mtime?.toMillis?.() ?? page?.file?.mtime ?? 0;

  const selectionKey = slug || path;

  return {
    id: selectionKey,
    selection_key: selectionKey,

    path,
    name: title,
    title,
    slug,

    slug_prefix: slugPrefixForSlug(slug),

    class: asText(page?.class, CONFIG.defaultClass),
    status: asText(page?.status, CONFIG.defaultStatus),
    stage: asText(page?.stage, CONFIG.defaultStage),
    process: asText(page?.process),

    modified: modifiedMillis,
    modified_display: modifiedMillis
      ? window.moment(modifiedMillis).format("YYYY-MM-DD HH:mm")
      : "",

    heading_key: context.heading_key,
    heading_path: context.heading_path,
    heading_level: context.heading_level,
    order: context.order,
    placement: context.placement || "toc",
  };
}

async function buildRowsFromToc() {
  const tocFile = getTocFile();

  if (!tocFile) {
    throw new Error("No table/content source file could be selected.");
  }

  const tocText = await app.vault.read(tocFile);

  const rows = [];
  const headings = [];
  const seenPaths = new Set();

  const currentHeadings = {
    1: "",
    2: "",
    3: "",
  };

  let order = 0;

  function currentHeadingParts() {
    return [
      currentHeadings[1],
      currentHeadings[2],
      currentHeadings[3],
    ].filter(Boolean);
  }

  function ensureHeading(level, title) {
    const parts = currentHeadingParts();
    const key = headingKey(parts);

    if (!key) return;

    if (!headings.some(heading => heading.key === key)) {
      headings.push({
        key,
        title,
        level,
        path: [...parts],
        order: headings.length,
      });
    }
  }

  for (const line of tocText.split(/\r?\n/)) {
    const headingMatch = String(line).match(/^(#{1,3})\s+(.+?)\s*$/);

    if (headingMatch) {
      const level = headingMatch[1].length;
      const title = headingMatch[2].trim();

      currentHeadings[level] = title;

      for (let child = level + 1; child <= 3; child += 1) {
        currentHeadings[child] = "";
      }

      ensureHeading(level, title);
      continue;
    }

    const links = extractWikiLinks(line);
    if (!links.length) continue;

    const parts = currentHeadingParts();
    const key = headingKey(parts) || "Contents";

    if (!headings.some(heading => heading.key === key)) {
      headings.push({
        key,
        title: headingLabel(parts),
        level: Math.max(parts.length, 1),
        path: parts.length ? [...parts] : ["Contents"],
        order: headings.length,
      });
    }

    for (const target of links) {
      const file = resolveMarkdownFileFromWikiTarget(target, tocFile.path);
      if (!file || isExcludedPath(file.path)) continue;

      const cleanPath = normalizePath(file.path);
      if (seenPaths.has(cleanPath)) continue;

      const page = pageForFile(file);
      if (!page) continue;

      seenPaths.add(cleanPath);

      rows.push(rowFromPage(page, file, {
        heading_key: key,
        heading_path: parts.length ? [...parts] : ["Contents"],
        heading_level: Math.max(parts.length, 1),
        order,
        placement: "toc",
      }));

      order += 1;
    }
  }

  return {
    rows,
    headings,
    tocFile,
    tocPaths: seenPaths,
  };
}

function buildUnplacedRows(tocPaths, tocFile) {
  const unplacedRows = [];
  const tocPath = normalizePath(tocFile?.path);
  const queryPathClean = normalizePath(queryPath);

  for (const file of candidateMarkdownFiles()) {
    const cleanPath = normalizePath(file.path);

    if (!cleanPath) continue;
    if (cleanPath === tocPath) continue;
    if (cleanPath === queryPathClean) continue;
    if (tocPaths.has(cleanPath)) continue;

    const page = pageForFile(file);
    if (!page) continue;

    const slug = asText(page?.slug);
    if (!slugMatchesCriteria(slug)) continue;

    unplacedRows.push(rowFromPage(page, file, {
      heading_key: "Not in table of contents",
      heading_path: ["Not in table of contents"],
      heading_level: 1,
      order: 1000000 + unplacedRows.length,
      placement: "unplaced",
    }));
  }

  return unplacedRows.sort((a, b) =>
    String(a.slug || a.title || a.path).localeCompare(String(b.slug || b.title || b.path))
  );
}

function serializeIndexRow(row) {
  return {
    selection_key: row.selection_key,
    slug: row.slug,
    title: row.title,
    path: row.path,
    heading: row.heading_key,
    heading_path: row.heading_path,
    placement: row.placement,
    slug_prefix: row.slug_prefix,
    class: row.class,
    status: row.status,
    stage: row.stage,
    process: row.process,
    modified: row.modified_display,
    order: row.order,
  };
}

function savedSelectionExtras({ rows }) {
  return {
    ordering: "table-of-contents",
    toc_path: SELECTED_TOC_FILE.path,
    slug_prefixes: CONFIG.slugPrefixes,
    displayed_count: rows.length,
    toc_count: rows.filter(row => row.placement === "toc").length,
    unplaced_count: rows.filter(row => row.placement === "unplaced").length,
  };
}

function rowBelongsToHeading(row, heading) {
  const headingPath = heading.path || [];
  const rowPath = row.heading_path || [];

  if (headingPath.length > rowPath.length) return false;

  return headingPath.every((part, index) => rowPath[index] === part);
}

function rowsForHeading(displayedRows, heading) {
  return displayedRows.filter(row => rowBelongsToHeading(row, heading));
}

function sortRowsByTocOrder(rows) {
  return [...rows].sort((a, b) => {
    const placementDiff = String(a.placement || "toc").localeCompare(String(b.placement || "toc"));
    if (placementDiff !== 0) return placementDiff;

    if (a.placement === "unplaced" || b.placement === "unplaced") {
      return String(a.slug || a.title || a.path).localeCompare(String(b.slug || b.title || b.path));
    }

    return Number(a.order || 0) - Number(b.order || 0);
  });
}

function renderHeadingBlock(parent, heading, headingRows, api) {
  if (!headingRows.length) return;

  const section = parent.createDiv();
  section.style.marginBottom = "1em";
  section.style.marginLeft = `${Math.max(0, heading.level - 1) * 1.25}em`;

  const headingRow = section.createDiv();
  headingRow.style.display = "flex";
  headingRow.style.alignItems = "center";
  headingRow.style.gap = "0.6em";
  headingRow.style.marginBottom = "0.4em";

  const checkedCount = headingRows.filter(row =>
    api.model.selectedKeys.has(row.selection_key)
  ).length;

  const groupBox = headingRow.createEl("input", { type: "checkbox" });
  setTriState(groupBox, checkedCount, headingRows.length);

  groupBox.onchange = async () => {
    for (const row of headingRows) {
      if (groupBox.checked) api.model.selectedKeys.add(row.selection_key);
      else api.model.selectedKeys.delete(row.selection_key);
    }

    await api.saveCurrentState({ quiet: true, action: "selection" });
    api.render();
  };

  const headingTag = heading.level === 1
    ? "h2"
    : heading.level === 2
      ? "h3"
      : "h4";

  const label = headingRow.createEl(headingTag, {
    text: heading.title,
  });

  label.style.margin = "0";

  const countText = headingRow.createEl("span");
  countText.style.opacity = "0.75";
  countText.setText(`(${checkedCount}/${headingRows.length})`);
}

function renderRowsTable(parent, rows, api) {
  const sortedRows = sortRowsByTocOrder(rows);

  const tableWrap = parent.createDiv();
  tableWrap.style.overflowX = "auto";
  tableWrap.style.marginBottom = "1.2em";

  const table = tableWrap.createEl("table");
  table.classList.add("dataview", "table-view-table");
  table.style.width = "100%";

  const thead = table.createEl("thead");
  const headRow = thead.createEl("tr");

  [
    "",
    "Title",
    "Class",
    "Status",
    "Stage",
  ].forEach(text => headRow.createEl("th", { text }));

  const tbody = table.createEl("tbody");

  for (const row of sortedRows) {
    const tr = tbody.createEl("tr");

    const selectCell = tr.createEl("td");
    const itemBox = selectCell.createEl("input", { type: "checkbox" });
    itemBox.checked = api.model.selectedKeys.has(row.selection_key);

    itemBox.onchange = async () => {
      if (itemBox.checked) api.model.selectedKeys.add(row.selection_key);
      else api.model.selectedKeys.delete(row.selection_key);

      await api.saveCurrentState({ quiet: true, action: "selection" });
      api.render();
    };

    const noteCell = tr.createEl("td");
    api.createInternalLink(noteCell, row.path, row.title);

    tr.createEl("td", { text: row.class });
    tr.createEl("td", { text: row.status });
    tr.createEl("td", { text: row.stage });
  }
}

function renderIndexResults(parent, displayedRows, api) {
  const tocRows = displayedRows.filter(row => row.placement !== "unplaced");
  const unplacedRows = displayedRows.filter(row => row.placement === "unplaced");

  const orderedHeadings = [...TOC_HEADINGS].sort((a, b) =>
    Number(a.order || 0) - Number(b.order || 0)
  );

  const renderedRowKeys = new Set();

  for (const heading of orderedHeadings) {
    const directRows = sortRowsByTocOrder(
      tocRows.filter(row => row.heading_key === heading.key)
    );

    const subtreeRows = rowsForHeading(tocRows, heading);

    if (!directRows.length && !subtreeRows.length) continue;

    renderHeadingBlock(parent, heading, subtreeRows, api);

    if (directRows.length) {
      const section = parent.createDiv();
      section.style.marginLeft = `${Math.max(0, heading.level - 1) * 1.25}em`;

      renderRowsTable(section, directRows, api);

      for (const row of directRows) {
        renderedRowKeys.add(row.selection_key);
      }
    }
  }

  const orphanRows = tocRows.filter(row => !renderedRowKeys.has(row.selection_key));

  if (orphanRows.length) {
    const heading = {
      key: "Contents",
      title: "Contents",
      level: 1,
      path: ["Contents"],
      order: 999999,
    };

    renderHeadingBlock(parent, heading, orphanRows, api);
    renderRowsTable(parent, orphanRows, api);
  }

  if (unplacedRows.length) {
    const heading = {
      key: "Not in table of contents",
      title: "Not in table of contents",
      level: 1,
      path: ["Not in table of contents"],
      order: 1000000,
    };

    renderHeadingBlock(parent, heading, unplacedRows, api);
    renderRowsTable(parent, unplacedRows, api);
  }
}

function renderSelectedTocLink(parent, api) {
  const sourceWrap = parent.createDiv();
  sourceWrap.style.display = "flex";
  sourceWrap.style.alignItems = "center";
  sourceWrap.style.gap = "0.4em";
  sourceWrap.style.marginBottom = "0.8em";

  sourceWrap.createEl("span", { text: "Source:" });
  api.createInternalLink(sourceWrap, SELECTED_TOC_FILE.path, SELECTED_TOC_FILE.basename);
}

function renderUnicodeReference(parent) {
  const details = parent.createEl("details");
  details.style.margin = "0.8em 0";

  details.createEl("summary", { text: "Unicode symbol reference" });

  const table = details.createEl("table");
  table.classList.add("dataview", "table-view-table");
  table.style.marginTop = "0.5em";

  const thead = table.createEl("thead");
  const headRow = thead.createEl("tr");
  ["Symbol", "Code", "Meaning"].forEach(text => headRow.createEl("th", { text }));

  const tbody = table.createEl("tbody");
  for (const item of CONFIG.unicodeReference) {
    const tr = tbody.createEl("tr");
    tr.createEl("td", { text: item.symbol });
    tr.createEl("td", { text: item.code });
    tr.createEl("td", { text: item.meaning });
  }
}

async function saveSelectionManifest(api) {
  await api.saveDataviewSelection({
    operation: "content-index",
    queryName: "Content Index",
    namespace: "content-index",
    selectionSource: "content-index",
    selectionKind: "content-index",
    selectionKey: "selection_key",
    serializeRow: serializeIndexRow,
    options: {
      toc_path: SELECTED_TOC_FILE.path,
      ordering: "table-of-contents",
      slug_prefixes: CONFIG.slugPrefixes,
      filters: ["slug_prefix", "class", "status", "stage"],
    },
    savedSelectionExtras({ rows }) {
      return savedSelectionExtras({ rows });
    }
  });
}

const tocBuild = await buildRowsFromToc();
const unplacedRows = buildUnplacedRows(tocBuild.tocPaths, tocBuild.tocFile);
const rows = [...tocBuild.rows, ...unplacedRows];
const TOC_HEADINGS = tocBuild.headings;
const SELECTED_TOC_FILE = tocBuild.tocFile;

if (!rows.length) {
  dv.container.innerHTML = "";
  dv.paragraph(`No Markdown files linked from ${SELECTED_TOC_FILE.path}, and no files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`);
  return;
}

await renderSelectionQuery({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,

  title: "Content Index",
  namespace: "content-index",
  bridgeName: "__contentIndexSelection",

  vaultName,
  queryPath,
  stateVersion: 1,
  tempRoot: CONFIG.tempRoot,

  rows,
  columns: [],

  filterFields: [
    { key: "slug_prefix", title: "Slug prefix" },
    { key: "class", title: "Class" },
    { key: "status", title: "Status" },
    { key: "stage", title: "Stage" },
  ],

  sortModes: [
    ["toc", "TOC order"],
  ],

  defaultSortMode: "toc",

  selectionKind: "content-index",
  selectionKey: "selection_key",
  serializeRow: serializeIndexRow,
  savedSelectionExtras({ rows }) {
    return savedSelectionExtras({ rows });
  },

  emptyMessage: `No Markdown files linked from ${SELECTED_TOC_FILE.path} were found.`,
  noMatchesMessage: "No matching files.",

  summaryText({ displayedRows, selectedRows }) {
    const tocCount = displayedRows.filter(row => row.placement === "toc").length;
    const unplacedCount = displayedRows.filter(row => row.placement === "unplaced").length;
    return `${tocCount} TOC file(s) · ${unplacedCount} not in TOC · ${selectedRows.length} checked`;
  },

  renderActions(parent, api) {
    renderSelectedTocLink(parent, api);
    renderUnicodeReference(parent);

    const saveButton = parent.createEl("button", { text: "Save selection manifest" });
    saveButton.onclick = async () => {
      await saveSelectionManifest(api);
    };
  },

  renderResults: renderIndexResults,

  debug: CONFIG.debug
});
```