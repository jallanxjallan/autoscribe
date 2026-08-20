"use strict";

function activeInstructionSlugs(app) {
  const slugs = [];
  const seen = new Set();

  for (const file of app.vault.getMarkdownFiles()) {
    const frontmatter = app.metadataCache.getFileCache(file)?.frontmatter || {};
    const slug = String(frontmatter.slug || "").trim();
    if (!slug || seen.has(slug)) continue;

    const declared = String(
      frontmatter.record || frontmatter.type || frontmatter.kind || ""
    ).trim().toLowerCase();
    if (declared && declared !== "instruction") continue;

    seen.add(slug);
    slugs.push(slug);
  }

  return slugs.sort();
}

module.exports = { activeInstructionSlugs };
