"use strict";

const { makeSlug } = require("../lib/slug");

function splitFrontmatter(markdown) {
  const text = String(markdown || "").replace(/\r\n/g, "\n");
  if (!text.startsWith("---\n")) {
    return { frontmatter: "", body: text, hasFrontmatter: false };
  }

  const end = text.indexOf("\n---\n", 4);
  if (end === -1) {
    return { frontmatter: "", body: text, hasFrontmatter: false };
  }

  return {
    frontmatter: text.slice(4, end),
    body: text.slice(end + 5),
    hasFrontmatter: true,
  };
}

function renderString(value, { title, slugPrefix } = {}) {
  let detectedPrefix = String(slugPrefix || "").trim();
  let rendered = String(value ?? "");

  rendered = rendered.replace(
    /<%\s*tp\.user\.make_slug\(tp,\s*["']([^"']+)["']\s*\)\s*%>/g,
    (_match, templatePrefix) => {
      const prefix = detectedPrefix || String(templatePrefix || "").trim();
      if (!prefix) throw new Error("Template slug prefix is blank.");
      detectedPrefix = prefix;
      return makeSlug(prefix, title);
    }
  );

  rendered = rendered.replace(/\{\{title\}\}/g, String(title || ""));
  return { value: rendered, slugPrefix: detectedPrefix };
}

function renderValue(value, context) {
  if (typeof value === "string") {
    return renderString(value, context);
  }

  if (Array.isArray(value)) {
    let prefix = String(context.slugPrefix || "").trim();
    const output = value.map((item) => {
      const rendered = renderValue(item, { ...context, slugPrefix: prefix });
      prefix = rendered.slugPrefix || prefix;
      return rendered.value;
    });
    return { value: output, slugPrefix: prefix };
  }

  if (value && typeof value === "object") {
    let prefix = String(context.slugPrefix || "").trim();
    const output = {};
    for (const [key, item] of Object.entries(value)) {
      const rendered = renderValue(item, { ...context, slugPrefix: prefix });
      prefix = rendered.slugPrefix || prefix;
      output[key] = rendered.value;
    }
    return { value: output, slugPrefix: prefix };
  }

  return { value, slugPrefix: String(context.slugPrefix || "").trim() };
}

async function loadTemplate({ app, templatePath, title, slugPrefix } = {}) {
  if (!app) throw new Error("loadTemplate requires app.");
  if (!templatePath) throw new Error("loadTemplate requires templatePath.");

  const templateFile = app.vault.getAbstractFileByPath(templatePath);
  if (!templateFile || templateFile.extension !== "md") {
    throw new Error(`Template not found: ${templatePath}`);
  }

  const raw = await app.vault.cachedRead(templateFile);
  const split = splitFrontmatter(raw);

  let parsed = {};
  if (split.hasFrontmatter && split.frontmatter.trim()) {
    try {
      const { parseYaml } = require("obsidian");
      parsed = parseYaml(split.frontmatter) || {};
    } catch (error) {
      const cached = app.metadataCache.getFileCache(templateFile)?.frontmatter;
      if (!cached) {
        throw new Error(
          `Could not parse frontmatter from template ${templatePath}: ${error?.message || String(error)}`
        );
      }
      parsed = { ...cached };
    }
  }

  const renderedFrontmatter = renderValue(parsed, { title, slugPrefix });
  const renderedBody = renderString(split.body, {
    title,
    slugPrefix: renderedFrontmatter.slugPrefix,
  });

  return {
    templatePath,
    frontmatter: renderedFrontmatter.value,
    body: renderedBody.value,
    slugPrefix: renderedBody.slugPrefix,
  };
}

function mergeFrontmatter(target, updates) {
  for (const [key, value] of Object.entries(updates || {})) {
    if (value === undefined) continue;
    target[key] = value;
  }
}

function normalizedInsertion(body) {
  const text = String(body || "").replace(/^\n+|\n+$/g, "");
  return text ? `${text}\n` : "";
}

async function appendBody(app, file, body) {
  const insertion = normalizedInsertion(body);
  if (!insertion) return;

  await app.vault.process(file, (current) => {
    const separator = current.endsWith("\n\n")
      ? ""
      : current.endsWith("\n")
        ? "\n"
        : "\n\n";
    return `${current}${separator}${insertion}`;
  });
}

async function applyTemplateToFile({
  app,
  targetPath,
  templatePath,
  slugPrefix,
  frontmatterOverrides = {},
  editor = null,
} = {}) {
  if (!app) throw new Error("applyTemplateToFile requires app.");
  if (!targetPath) throw new Error("applyTemplateToFile requires targetPath.");
  if (!templatePath) throw new Error("applyTemplateToFile requires templatePath.");

  const file = app.vault.getAbstractFileByPath(targetPath);
  if (!file || file.extension !== "md") {
    throw new Error(`Target not found: ${targetPath}`);
  }

  const template = await loadTemplate({
    app,
    templatePath,
    title: file.basename,
    slugPrefix,
  });

  const updates = { ...template.frontmatter, ...frontmatterOverrides };

  await app.fileManager.processFrontMatter(file, (frontmatter) => {
    mergeFrontmatter(frontmatter, updates);
  });

  const insertion = normalizedInsertion(template.body);
  if (insertion) {
    if (editor && app.workspace.getActiveFile()?.path === file.path) {
      const cursor = editor.getCursor();
      editor.replaceRange(insertion, cursor);
      editor.setCursor(editor.offsetToPos(editor.posToOffset(cursor) + insertion.length));
    } else {
      await appendBody(app, file, insertion);
    }
  }

  return {
    path: file.path,
    templatePath,
    slug: String(updates.slug || ""),
    class: String(updates.class || ""),
  };
}

module.exports = {
  splitFrontmatter,
  loadTemplate,
  applyTemplateToFile,
};
