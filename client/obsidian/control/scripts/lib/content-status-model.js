"use strict";

const { makeContentQueryUtils } = require("./content-query-utils.js");

function makeContentStatusModel({ app, dv, config }) {
  const utils = makeContentQueryUtils({ app, dv, config });
  const {
    asText,
    normalizePath,
    titleForPage,
    modifiedMillisForPage,
    modifiedDisplayForMillis,
    alphaCompareRows,
    candidateMarkdownFiles,
    pageForFile,
    slugPrefixForSlug,
  } = utils;

  function processForPage(page) {
    // Git-derived process state goes here later. Frontmatter is the production stub.
    return asText(page?.process, config.defaultProcess);
  }

  function sluggedPageForFile(file) {
    const page = pageForFile(file);
    if (!page) return null;

    const slug = asText(page.slug);
    if (!slug) return null;

    return { file, page, slug };
  }

  function rowFromPage(file, page, slug) {
    const modifiedMillis = modifiedMillisForPage(page);
    const title = titleForPage(page, file.basename);

    return {
      id: slug,
      selection_key: slug,
      path: normalizePath(file.path),
      name: title,
      title,
      slug,
      slug_prefix: slugPrefixForSlug(slug),
      status: asText(page.status, config.defaultStatus),
      stage: asText(page.stage, config.defaultStage),
      process: processForPage(page),
      modified: modifiedMillis,
      modified_display: modifiedDisplayForMillis(modifiedMillis),
    };
  }

  function buildRows() {
    return candidateMarkdownFiles()
      .map(sluggedPageForFile)
      .filter(Boolean)
      .map(({ file, page, slug }) => rowFromPage(file, page, slug));
  }

  function serializeRow(row) {
    return {
      selection_key: row.slug,
      slug: row.slug,
      slug_prefix: row.slug_prefix,
      title: row.title,
      path: row.path,
      status: row.status,
      stage: row.stage,
      process: row.process,
      modified: row.modified_display,
    };
  }

  function savedSelectionExtras({ rows }) {
    return {
      ordering: "content-status",
      displayed_count: rows.length,
      filters: ["status", "stage", "process"],
      sort_modes: ["title", "modified"],
    };
  }

  function sortRows(rows, mode) {
    const copy = [...rows];

    if (mode === "title-desc") return copy.sort((a, b) => alphaCompareRows(b, a));
    if (mode === "modified-desc") return copy.sort((a, b) => Number(b.modified || 0) - Number(a.modified || 0));
    if (mode === "modified-asc") return copy.sort((a, b) => Number(a.modified || 0) - Number(b.modified || 0));

    return copy.sort(alphaCompareRows);
  }

  function build() {
    return {
      rows: buildRows(),
      serializeRow,
      savedSelectionExtras,
      sortRows,
    };
  }

  return { build };
}

module.exports = { makeContentStatusModel };
