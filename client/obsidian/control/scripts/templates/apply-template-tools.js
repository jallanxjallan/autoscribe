"use strict";

const { makeSlug } = require("../lib/slug");

function splitFrontmatter(markdown) {
  const text = String(markdown || "").replace(/\r\n/g, "\n");
  if (!text.startsWith("---\n")) return { frontmatter: "", body: text, hasFrontmatter: false };
  const end = text.indexOf("\n---\n", 4);
  if (end === -1) return { frontmatter: "", body: text, hasFrontmatter: false };
  return { frontmatter: text.slice(4, end), body: text.slice(end + 5), hasFrontmatter: true };
}

function parseScalar(value) {
  const text = String(value ?? "").trim();
  if (text === "") return "";
  if (text === "[]") return [];
  if (text === "{}") return {};
  if (text === "true") return true;
  if (text === "false") return false;
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}

function parseSimpleFrontmatter(frontmatter) {
  const out = {};
  for (const rawLine of String(frontmatter || "").split("\n")) {
    if (!rawLine.trim() || /^\s/.test(rawLine) || rawLine.trim().startsWith("#")) continue;
    const match = rawLine.match(/^([A-Za-z0-9_-]+):\s*(.*?)\s*$/);
    if (!match) continue;
    out[match[1]] = parseScalar(match[2]);
  }
  return out;
}

function extractCreateSpec(templateFm) {
  const create = {};
  if (typeof templateFm.slug === "string") {
    const match = templateFm.slug.match(/make_slug\([^,]+,\s*["']([^"']+)["']/);
    if (match) create.slugPrefix = match[1];
  }
  return create;
}

async function loadTemplateFrontmatter({ app, templatePath } = {}) {
  if (!app) throw new Error("loadTemplateFrontmatter requires app.");
  if (!templatePath) throw new Error("loadTemplateFrontmatter requires templatePath.");

  const file = app.vault.getAbstractFileByPath(templatePath);
  if (!file) throw new Error(`Template not found: ${templatePath}`);

  const text = await app.vault.cachedRead(file);
  const split = splitFrontmatter(text);
  const templateFm = parseSimpleFrontmatter(split.frontmatter);
  const create = extractCreateSpec(templateFm);

  return { templateFm, create, templatePath };
}

async function applyTemplateToFile({ app, targetPath, templateFm = {}, create = {} } = {}) {
  if (!app) throw new Error("applyTemplateToFile requires app.");
  if (!targetPath) throw new Error("applyTemplateToFile requires targetPath.");

  const file = app.vault.getAbstractFileByPath(targetPath);
  if (!file) throw new Error(`Target not found: ${targetPath}`);

  const updates = { ...templateFm };
  if (create.slugPrefix && (!updates.slug || String(updates.slug).includes("<%"))) {
    updates.slug = makeSlug(create.slugPrefix, file.basename || targetPath);
  }

  await app.fileManager.processFrontMatter(file, (frontmatter) => {
    for (const [key, value] of Object.entries(updates)) {
      if (value === undefined) continue;
      frontmatter[key] = value;
    }
  });

  return { path: targetPath, slug: updates.slug || "" };
}

module.exports = {
  splitFrontmatter,
  parseSimpleFrontmatter,
  loadTemplateFrontmatter,
  applyTemplateToFile,
};
