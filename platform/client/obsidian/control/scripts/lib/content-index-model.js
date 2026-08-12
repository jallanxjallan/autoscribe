"use strict";

const { makeContentQueryUtils } = require("./content-query-utils.js");

function makeContentIndexModel({ app, dv, queryPath, config }) {
  const utils = makeContentQueryUtils({ app, dv, config });
  const {
    asText,
    asList,
    normalizePath,
    titleForPage,
    modifiedMillisForPage,
    modifiedDisplayForMillis,
    getRootMarkdownCandidates,
    resolveMarkdownFileFromWikiTarget,
    unicodeFormatForText,
    unicodeSymbolForText,
    unicodeDisplayForText,
    candidateMarkdownFiles,
    pageForFile,
    slugPrefixForSlug,
    slugMatchesCriteria,
    headingKey,
    headingLabel,
    localeCompareText,
  } = utils;

  function getTocFile() {
    const configuredPath = asText(config.tocPath).trim();

    if (configuredPath) {
      const cleanTocPath = normalizePath(configuredPath);
      const configuredFile = app.vault.getMarkdownFiles().find(file =>
        normalizePath(file.path) === cleanTocPath || file.name === cleanTocPath
      );

      if (configuredFile) return configuredFile;
      throw new Error(`Configured table/content file not found: ${config.tocPath}`);
    }

    const candidates = getRootMarkdownCandidates()
      .filter(file => utils.tocPriorityScore(file) > 0);

    return candidates.length ? candidates[0] : null;
  }

  function cleanTocTarget(target) {
    return String(target || "")
      .replace(/\.md$/i, "")
      .trim();
  }

  function decodeObsidianAppPath(url) {
    const raw = String(url || "").trim();
    if (!raw.startsWith("app://obsidian.md/")) return "";

    try {
      return decodeURIComponent(raw.replace(/^app:\/\/obsidian\.md\//, ""))
        .replace(/\.md$/i, "")
        .trim();
    } catch (_error) {
      return raw.replace(/^app:\/\/obsidian\.md\//, "")
        .replace(/\.md$/i, "")
        .trim();
    }
  }

  function extractTocTargets(line) {
    const targets = [];
    const seen = new Set();
    const text = String(line || "");

    function addTarget(target, kind = "wiki") {
      const clean = cleanTocTarget(target);
      if (!clean) return;

      const key = `${kind}:${clean.toLowerCase()}`;
      if (seen.has(key)) return;

      seen.add(key);
      targets.push({ target: clean, kind });
    }

    const wikiRegex = /\[\[([^\]]+)\]\]/g;
    let match;
    while ((match = wikiRegex.exec(text)) !== null) {
      addTarget(match[1].split("|")[0].split("#")[0].trim(), "wiki");
    }

    const markdownRegex = /\[[^\]]*\]\(([^)]+)\)/g;
    while ((match = markdownRegex.exec(text)) !== null) {
      const decoded = decodeObsidianAppPath(match[1]);
      if (decoded) addTarget(decoded, "markdown");
    }

    return targets;
  }

  function tocMembershipAliasesForTarget(target) {
    const clean = cleanTocTarget(target);
    if (!clean) return [];

    const noExt = normalizePath(clean).replace(/\.md$/i, "");
    const basename = noExt.split("/").filter(Boolean).pop() || noExt;

    return [noExt, basename]
      .map(value => value.toLowerCase().trim())
      .filter(Boolean);
  }

  function tocMembershipAliasesForFile(file) {
    const cleanPath = normalizePath(file?.path).replace(/\.md$/i, "");
    const basename = String(file?.basename || "").trim();

    return [cleanPath, basename]
      .map(value => value.toLowerCase().trim())
      .filter(Boolean);
  }

  function addTocMembership(tocKeys, file, target) {
    for (const key of tocMembershipAliasesForTarget(target)) tocKeys.add(key);
    if (file) {
      for (const key of tocMembershipAliasesForFile(file)) tocKeys.add(key);
    }
  }

  function fileMatchesTocMembership(file, tocPaths, tocKeys) {
    const cleanPath = normalizePath(file.path);
    if (tocPaths.has(cleanPath)) return true;

    return tocMembershipAliasesForFile(file).some(key => tocKeys.has(key));
  }

  function pageMatchesIndexCriteria(page) {
    const slug = asText(page?.slug);
    return slugMatchesCriteria(slug);
  }

  function rowFromPage(page, file, context) {
    const path = normalizePath(file.path);
    const slug = asText(page?.slug);
    const title = titleForPage(page, file.basename);
    const modifiedMillis = modifiedMillisForPage(page);

    const rawTagValues = asList(page?.tags || page?.tag);
    const tagValues = rawTagValues.length ? rawTagValues : [config.defaultTags];
    const selectionKey = slug || path;
    const layoutComponent = context.layout_component
      || context.unicode_display
      || unicodeDisplayForText(title)
      || config.defaultLayoutComponent;

    return {
      id: selectionKey,
      selection_key: selectionKey,
      path,
      name: title,
      title,
      slug,
      slug_prefix: slugPrefixForSlug(slug),
      tag_values: tagValues,
      tags_display: tagValues.join(", "),
      unicode_format: context.unicode_format || unicodeFormatForText(title),
      unicode_symbol: context.unicode_symbol || unicodeSymbolForText(title),
      unicode_display: context.unicode_display || unicodeDisplayForText(title),
      layout_component: layoutComponent,
      class: asText(page?.class, config.defaultClass),
      modified: modifiedMillis,
      modified_display: modifiedDisplayForMillis(modifiedMillis),
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
      return {
        rows: [],
        headings: [],
        tocFile: null,
        tocPaths: new Set(),
        tocKeys: new Set(),
        linkHealth: { missing: [], duplicates: [] },
        noToc: true,
      };
    }

    const tocText = await app.vault.read(tocFile);
    const rows = [];
    const headings = [];
    const seenPaths = new Set();
    const tocPaths = new Set();
    const tocKeys = new Set();
    const placementsByPath = new Map();
    const linkHealth = { missing: [], duplicates: [] };
    const currentHeadings = { 1: "", 2: "", 3: "" };
    let order = 0;

    function currentHeadingParts() {
      return [currentHeadings[1], currentHeadings[2], currentHeadings[3]].filter(Boolean);
    }

    function ensureHeading(level, title) {
      const parts = currentHeadingParts();
      const key = headingKey(parts);
      if (!key) return;

      if (!headings.some(heading => heading.key === key)) {
        headings.push({ key, title, level, path: [...parts], order: headings.length });
      }
    }

    function addPlacement(file, target, lineNumber, lineText, headingKeyValue, headingPath) {
      const cleanPath = normalizePath(file.path);
      const placement = { path: cleanPath, basename: file.basename, target, lineNumber, lineText, heading_key: headingKeyValue, heading_path: headingPath };
      const placements = placementsByPath.get(cleanPath) || [];
      placements.push(placement);
      placementsByPath.set(cleanPath, placements);
      return placements;
    }

    const tocLines = tocText.split(/\r?\n/);

    for (let lineIndex = 0; lineIndex < tocLines.length; lineIndex += 1) {
      const line = tocLines[lineIndex];
      const lineNumber = lineIndex + 1;
      const headingMatch = String(line).match(/^(#{1,3})\s+(.+?)\s*$/);

      if (headingMatch) {
        const level = headingMatch[1].length;
        const title = headingMatch[2].trim();
        currentHeadings[level] = title;

        for (let child = level + 1; child <= 3; child += 1) currentHeadings[child] = "";
        ensureHeading(level, title);
        continue;
      }

      const targets = extractTocTargets(line);
      if (!targets.length) continue;

      const lineUnicodeFormat = unicodeFormatForText(line);
      const lineUnicodeSymbol = unicodeSymbolForText(line);
      const lineUnicodeDisplay = unicodeDisplayForText(line);
      const parts = currentHeadingParts();
      const key = headingKey(parts) || "Contents";
      const headingPath = parts.length ? [...parts] : ["Contents"];

      if (!headings.some(heading => heading.key === key)) {
        headings.push({ key, title: headingLabel(parts), level: Math.max(parts.length, 1), path: headingPath, order: headings.length });
      }

      for (const { target } of targets) {
        const file = resolveMarkdownFileFromWikiTarget(target, tocFile.path);
        addTocMembership(tocKeys, file, target);

        if (!file) {
          linkHealth.missing.push({ target, lineNumber, lineText: String(line || "").trim(), heading_key: key, heading_path: headingPath });
          continue;
        }

        const cleanPath = normalizePath(file.path);
        tocPaths.add(cleanPath);

        if (utils.isExcludedPath(file.path)) continue;

        const placements = addPlacement(file, target, lineNumber, String(line || "").trim(), key, headingPath);
        if (placements.length === 2) {
          linkHealth.duplicates.push({ path: cleanPath, basename: file.basename, placements });
        } else if (placements.length > 2) {
          linkHealth.duplicates = linkHealth.duplicates.map(item =>
            item.path === cleanPath ? { ...item, placements } : item
          );
        }

        if (seenPaths.has(cleanPath)) continue;

        const page = pageForFile(file);
        if (!page) continue;
        if (!pageMatchesIndexCriteria(page)) continue;

        seenPaths.add(cleanPath);
        rows.push(rowFromPage(page, file, {
          heading_key: key,
          heading_path: headingPath,
          heading_level: Math.max(parts.length, 1),
          order,
          placement: "toc",
          unicode_format: lineUnicodeFormat,
          unicode_symbol: lineUnicodeSymbol,
          unicode_display: lineUnicodeDisplay,
        }));
        order += 1;
      }
    }

    return { rows, headings, tocFile, tocPaths, tocKeys, linkHealth, noToc: false };
  }

  function buildUnplacedRows(tocPaths, tocKeys, tocFile) {
    const unplacedRows = [];
    const tocPath = normalizePath(tocFile?.path);
    const queryPathClean = normalizePath(queryPath);

    for (const file of candidateMarkdownFiles()) {
      const cleanPath = normalizePath(file.path);
      if (!cleanPath) continue;
      if (cleanPath === tocPath) continue;
      if (cleanPath === queryPathClean) continue;
      if (fileMatchesTocMembership(file, tocPaths, tocKeys)) continue;

      const page = pageForFile(file);
      if (!page) continue;

      if (!pageMatchesIndexCriteria(page)) continue;

      unplacedRows.push(rowFromPage(page, file, {
        heading_key: "Not in table of contents",
        heading_path: ["Not in table of contents"],
        heading_level: 1,
        order: 1000000 + unplacedRows.length,
        placement: "unplaced",
      }));
    }

    return unplacedRows.sort((a, b) => localeCompareText(a.slug || a.title || a.path, b.slug || b.title || b.path));
  }

  function buildAlphabeticalRows() {
    const rows = [];
    const queryPathClean = normalizePath(queryPath);

    for (const file of candidateMarkdownFiles()) {
      const cleanPath = normalizePath(file.path);
      if (!cleanPath) continue;
      if (cleanPath === queryPathClean) continue;

      const page = pageForFile(file);
      if (!page) continue;

      if (!pageMatchesIndexCriteria(page)) continue;

      rows.push(rowFromPage(page, file, {
        heading_key: "Contents",
        heading_path: ["Contents"],
        heading_level: 1,
        order: rows.length,
        placement: "alphabetical",
      }));
    }

    return rows
      .sort((a, b) => localeCompareText(a.title || a.slug || a.path, b.title || b.slug || b.path))
      .map((row, index) => ({ ...row, order: index }));
  }

  function serializeRow(row) {
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
      tags: row.tag_values,
      tags_display: row.tags_display,
      layout_component: row.layout_component,
      unicode_format: row.unicode_format,
      unicode_symbol: row.unicode_symbol,
      unicode_display: row.unicode_display,
      modified: row.modified_display,
      order: row.order,
    };
  }

  function makeSavedSelectionExtras(selectedTocFile) {
    return function savedSelectionExtras({ rows }) {
      return {
        ordering: selectedTocFile ? "table-of-contents" : "alphabetical",
        toc_path: selectedTocFile?.path || "",
        slug_prefixes: config.slugPrefixes,
        displayed_count: rows.length,
        toc_count: rows.filter(row => row.placement === "toc").length,
        unplaced_count: rows.filter(row => row.placement === "unplaced").length,
        alphabetical_count: rows.filter(row => row.placement === "alphabetical").length,
      };
    };
  }

  function sortRowsByTocOrder(rows) {
    return [...rows].sort((a, b) => {
      const placementOrder = { toc: 0, alphabetical: 0, unplaced: 1 };
      const placementDiff = (placementOrder[a.placement] ?? 0) - (placementOrder[b.placement] ?? 0);
      if (placementDiff !== 0) return placementDiff;

      if (a.placement === "unplaced" || b.placement === "unplaced" || a.placement === "alphabetical" || b.placement === "alphabetical") {
        return localeCompareText(a.slug || a.title || a.path, b.slug || b.title || b.path);
      }

      return Number(a.order || 0) - Number(b.order || 0);
    });
  }

  async function build() {
    const tocBuild = await buildRowsFromToc();
    const selectedTocFile = tocBuild.tocFile;
    const unplacedRows = tocBuild.noToc ? [] : buildUnplacedRows(tocBuild.tocPaths, tocBuild.tocKeys, tocBuild.tocFile);
    const rows = tocBuild.noToc ? buildAlphabeticalRows() : [...tocBuild.rows, ...unplacedRows];
    const headings = tocBuild.noToc
      ? [{ key: "Contents", title: "Contents", level: 1, path: ["Contents"], order: 0 }]
      : tocBuild.headings;

    return {
      rows,
      headings,
      selectedTocFile,
      linkHealth: tocBuild.linkHealth,
      serializeRow,
      savedSelectionExtras: makeSavedSelectionExtras(selectedTocFile),
      sortRows: sortRowsByTocOrder,
    };
  }

  return { build };
}

module.exports = { makeContentIndexModel };
