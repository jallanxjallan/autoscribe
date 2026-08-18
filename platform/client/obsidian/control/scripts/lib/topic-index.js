const { loadConfig } = require("./config-loader.js");
function createTopicIndexLogic({ app, dv, pathMod, vaultBasePath, queryPath, config, rg }) {
  if (!app) throw new Error("createTopicIndexLogic requires app.");
  if (!dv) throw new Error("createTopicIndexLogic requires dv.");
  if (!pathMod) throw new Error("createTopicIndexLogic requires pathMod.");
  if (!vaultBasePath) throw new Error("createTopicIndexLogic requires vaultBasePath.");
  if (!queryPath) throw new Error("createTopicIndexLogic requires queryPath.");
  if (!config) throw new Error("createTopicIndexLogic requires config.");
  if (!rg || typeof rg.rgLines !== "function") throw new Error("createTopicIndexLogic requires rg.rgLines.");

  function asList(value) {
    if (value == null) return [];

    if (Array.isArray(value)) {
      return value.flatMap(asList);
    }

    if (
      typeof value === "object" &&
      typeof value[Symbol.iterator] === "function"
    ) {
      return Array.from(value).flatMap(asList);
    }

    const text = String(value).trim();
    return text ? [text] : [];
  }

  function uniqueSorted(values) {
    return [...new Set(
      values
        .map(value => String(value || "").trim())
        .filter(Boolean)
    )].sort((a, b) => a.localeCompare(b));
  }

  function asText(value, fallback = "") {
    const values = asList(value);
    return values.length ? values.join(", ") : fallback;
  }

  function normalizePath(path) {
    return String(path || "").replace(/^\/+/, "");
  }

  function normalizeSlug(value) {
    return asText(value).toLowerCase().trim();
  }

  function normalizeTag(value) {
    return String(value || "")
      .trim()
      .replace(/^#/, "");
  }

  function clearElement(element) {
    if (element?.empty) element.empty();
    else if (element) element.innerHTML = "";
  }

  function googleBookmarkIdFromText(value) {
    const text = String(value || "").trim();
    if (!text) return "";

    const bookmarkMatch = text.match(/(?:^|[#?&])bookmark=([^&#\s]+)/i);
    if (bookmarkMatch) {
      try {
        return decodeURIComponent(bookmarkMatch[1]).trim();
      } catch (_) {
        return String(bookmarkMatch[1] || "").trim();
      }
    }

    const idMatch = text.match(/\bid\.[A-Za-z0-9_-]+\b/i);
    return idMatch ? idMatch[0].trim() : "";
  }

  function isUnderscoreFolder(path) {
    return normalizePath(path)
      .split("/")
      .slice(0, -1)
      .some(part => part.startsWith(String(loadConfig("paths").excluded_folder_prefix || "_")));
  }

  function isExcludedPath(path) {
    const clean = normalizePath(path);

    if (isUnderscoreFolder(clean)) return true;

    return config.excludePaths.some(prefix => {
      const cleanPrefix = normalizePath(prefix).replace(/\/+$/, "");
      return clean === cleanPrefix || clean.startsWith(`${cleanPrefix}/`);
    });
  }

  function slugPrefixForSlug(slug) {
    const cleanSlug = normalizeSlug(slug);
    if (!cleanSlug) return "—";

    const explicitPrefix = config.slugPrefixes.find(prefix => {
      const cleanPrefix = String(prefix || "").toLowerCase().trim();
      return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
    });

    if (explicitPrefix) return String(explicitPrefix).toLowerCase().trim();

    return cleanSlug.split(/[.\-_/]/)[0] || "—";
  }

  function slugMatchesCriteria(slug) {
    const cleanSlug = normalizeSlug(slug);
    if (!cleanSlug) return false;

    return config.slugPrefixes.some(prefix => {
      const cleanPrefix = String(prefix || "").toLowerCase().trim();
      return cleanPrefix && cleanSlug.startsWith(cleanPrefix);
    });
  }

  function filenameStemForFile(file, fallback = "") {
    return (
      asText(file?.basename) ||
      asText(String(file?.name || "").replace(/\.[^.]+$/, "")) ||
      asText(fallback) ||
      asText(file?.path)
    );
  }

  function candidateMarkdownFiles() {
    return app.vault.getMarkdownFiles()
      .filter(file => !isExcludedPath(file.path))
      .filter(file => normalizePath(file.path) !== normalizePath(queryPath))
      .sort((a, b) => String(a.path).localeCompare(String(b.path)));
  }

  function pageForFile(file) {
    if (!file || isExcludedPath(file.path)) return null;
    return dv.page(file.path) || null;
  }

  function statusesForPage(page) {
    const statuses = uniqueSorted(asList(page?.status));
    return statuses.length ? statuses : [config.defaultStatus];
  }

  function tagsForPage(page) {
    const explicitTags = asList(page?.tags).map(normalizeTag).filter(Boolean);
    const fileTags = asList(page?.file?.tags).map(normalizeTag).filter(Boolean);
    const tags = uniqueSorted([...explicitTags, ...fileTags]);

    return tags.length ? tags : [config.defaultTag];
  }

  function topicsForPage(page) {
    const topics = uniqueSorted(asList(page?.topic));
    return topics.length ? topics : [config.defaultTopic];
  }

  function kindForPrefix(prefix) {
    if (prefix === "tpc") return "Topic";
    if (prefix === "fnd") return "Finding";
    return prefix || "—";
  }

  function entityRowFromPage(page, file) {
    const path = normalizePath(file.path);
    const slug = asText(page?.slug);
    const slugPrefix = slugPrefixForSlug(slug);
    const filename = filenameStemForFile(file);

    const statuses = statusesForPage(page);
    const tags = tagsForPage(page);
    const topics = topicsForPage(page);

    const modifiedMillis = page?.file?.mtime?.toMillis?.() ?? page?.file?.mtime ?? 0;

    return {
      id: slug,
      selection_key: slug,

      path,
      name: filename,
      title: filename,
      file_name: filename,
      slug,
      slug_prefix: slugPrefix,
      kind: kindForPrefix(slugPrefix),

      statuses,
      tags,
      topics,

      status_display: statuses.join(", "),
      tag_display: tags.join(", "),
      topic_display: topics.join(", "),

      modified: modifiedMillis,
      modified_display: modifiedMillis
        ? window.moment(modifiedMillis).format("YYYY-MM-DD HH:mm")
        : "",
    };
  }

  function buildEntityRows() {
    const rows = [];
    const seenSlugs = new Set();

    for (const file of candidateMarkdownFiles()) {
      const page = pageForFile(file);
      if (!page) continue;

      const slug = asText(page?.slug);
      if (!slugMatchesCriteria(slug)) continue;

      const cleanSlug = normalizeSlug(slug);
      if (seenSlugs.has(cleanSlug)) continue;
      seenSlugs.add(cleanSlug);

      rows.push(entityRowFromPage(page, file));
    }

    return rows.sort((a, b) => {
      const kindDiff = String(a.slug_prefix).localeCompare(String(b.slug_prefix));
      if (kindDiff !== 0) return kindDiff;

      return String(a.title || a.path).localeCompare(String(b.title || b.path));
    });
  }

  function buildFilterRows(entityRows) {
    const rows = [];

    for (const entity of entityRows) {
      for (const status of entity.statuses) {
        for (const tag of entity.tags) {
          for (const topic of entity.topics) {
            rows.push({
              ...entity,
              selection_key: entity.selection_key,
              status,
              tag,
              topic,
              entity,
              filter_key: `${entity.selection_key}::${status}::${tag}::${topic}`,
            });
          }
        }
      }
    }

    return rows;
  }

  function entityFromRow(row) {
    return row?.entity || row;
  }

  function uniqueEntityRows(rows) {
    const byKey = new Map();

    for (const row of rows) {
      const entity = entityFromRow(row);
      if (!entity?.selection_key) continue;
      if (!byKey.has(entity.selection_key)) byKey.set(entity.selection_key, entity);
    }

    return [...byKey.values()];
  }

  function uniqueSelectionKeys(rows) {
    return new Set(
      uniqueEntityRows(rows)
        .map(row => row.selection_key)
        .filter(Boolean)
    );
  }

  function serializeIndexRow(row) {
    const entity = entityFromRow(row);

    return {
      selection_key: entity.selection_key,
      slug: entity.slug,
      title: entity.title,
      path: entity.path,
      kind: entity.kind,
      slug_prefix: entity.slug_prefix,

      status: entity.statuses,
      status_display: entity.status_display,

      topic: entity.topics,
      topic_display: entity.topic_display,

      tag: entity.tags,
      tag_display: entity.tag_display,

      modified: entity.modified_display,
    };
  }

  function savedSelectionExtras({ rows }) {
    const entityRows = uniqueEntityRows(rows);

    return {
      ordering: String(loadConfig("queries").topic_index?.ordering || "kind-title"),
      slug_prefixes: config.slugPrefixes,
      displayed_count: entityRows.length,
      topic_count: entityRows.filter(row => row.slug_prefix === String(loadConfig("queries").topic_index?.topic_prefix || "tpc")).length,
      finding_count: entityRows.filter(row => row.slug_prefix === String(loadConfig("queries").topic_index?.finding_prefix || "fnd")).length,
    };
  }

  function groupRows(displayedRows) {
    const entityRows = uniqueEntityRows(displayedRows);

    const groupConfig = loadConfig("ui").topic_index_groups || {};
    const groups = Object.entries(groupConfig)
      .filter(([key]) => key !== "other")
      .map(([key, title]) => ({ key, title: String(title), rows: entityRows.filter(row => row.slug_prefix === key) }));

    const known = new Set(groups.flatMap(group => group.rows.map(row => row.selection_key)));
    const otherRows = entityRows.filter(row => !known.has(row.selection_key));

    if (otherRows.length) {
      groups.push({ key: "other", title: String(groupConfig.other || "Other"), rows: otherRows });
    }

    return groups.filter(group => group.rows.length);
  }

  function sortRows(rows) {
    return [...rows].sort((a, b) =>
      String(a.title || a.path).localeCompare(String(b.title || b.path))
    );
  }

  function rgBookmarkPaths(bookmarkId) {
    const bookmarkGlobs = loadConfig("queries").topic_index?.bookmark_globs || [];
    const runtimeDir = String(loadConfig("paths").runtime_dir || ".autoscribe");
    const globArgs = bookmarkGlobs.flatMap((pattern) => ["--glob", String(pattern).replace("{runtime_dir}", runtimeDir)]);
    const lines = rg.rgLines([
      "--files-with-matches",
      ...globArgs,
      bookmarkId,
      ".",
    ], { cwd: vaultBasePath });

    return uniqueSorted(
      lines.map(line => normalizePath(line.replace(/^\.\//, "")))
    );
  }

  function findBookmarkMatches(rawInput, entityRows) {
    const bookmarkId = googleBookmarkIdFromText(rawInput);
    if (!bookmarkId) return { bookmarkId: "", matches: [] };

    const paths = rgBookmarkPaths(bookmarkId);

    const matches = paths.map(path => {
      const existing = entityRows.find(row => normalizePath(row.path) === path);
      if (existing) return existing;

      const file = app.vault.getAbstractFileByPath(path);
      const page = pageForFile(file);

      return {
        selection_key: path,
        path,
        title: filenameStemForFile(file, path),
        slug: asText(page?.slug),
        slug_prefix: slugPrefixForSlug(page?.slug),
        kind: slugMatchesCriteria(page?.slug)
          ? kindForPrefix(slugPrefixForSlug(page?.slug))
          : "Unindexed",
      };
    });

    return { bookmarkId, matches };
  }

  function summaryText({ displayedRows, selectedRows }) {
    const displayedEntities = uniqueEntityRows(displayedRows);
    const displayedSelectedKeys = uniqueSelectionKeys(displayedRows);
    const selectedVisibleCount = [...displayedSelectedKeys]
      .filter(key => selectedRows.some(row => row.selection_key === key))
      .length;

    const topicCount = displayedEntities.filter(row => row.slug_prefix === "tpc").length;
    const findingCount = displayedEntities.filter(row => row.slug_prefix === "fnd").length;

    return `${topicCount} topic(s) · ${findingCount} finding(s) · ${selectedVisibleCount} checked`;
  }

  return {
    asList,
    asText,
    clearElement,
    normalizePath,
    googleBookmarkIdFromText,
    filenameStemForFile,
    slugPrefixForSlug,
    slugMatchesCriteria,
    kindForPrefix,
    buildEntityRows,
    buildFilterRows,
    entityFromRow,
    uniqueEntityRows,
    uniqueSelectionKeys,
    serializeIndexRow,
    savedSelectionExtras,
    groupRows,
    sortRows,
    findBookmarkMatches,
    summaryText,
  };
}

module.exports = { createTopicIndexLogic };
