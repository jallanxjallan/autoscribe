const { getFrontmatterValue } = require("./frontmatter");
const { getFolderPath, isPublicVaultPath } = require("./query-paths");
const { parseWikilinks } = require("./wikilinks");

function isMarkdownPathUnder(filePath, prefix) {
  return (
    typeof filePath === "string" &&
    filePath.startsWith(prefix) &&
    filePath.endsWith(".md")
  );
}

function getSlug(app, file) {
  return String(getFrontmatterValue(app, file, "slug", "") || "").trim();
}

function isPublicSluggedFile(app, file, { contentsPrefix = "contents/" } = {}) {
  return Boolean(
    file &&
    isMarkdownPathUnder(file.path, contentsPrefix) &&
    isPublicVaultPath(file.path) &&
    getSlug(app, file).length > 0
  );
}

function parseFenceComponent(line, { defaultComponent = "narrative" } = {}) {
  const match = String(line || "").match(/^\s*:::\s*(.*)$/);
  if (!match) return null;

  const rest = match[1].trim();
  if (!rest) return { kind: "close" };

  const attrText = rest.startsWith("{") && rest.endsWith("}")
    ? rest.slice(1, -1).trim()
    : rest;

  const classMatches = [...attrText.matchAll(/\.([A-Za-z0-9_-]+)/g)]
    .map(m => m[1].trim())
    .filter(Boolean);

  if (classMatches.length > 0) {
    return { kind: "open", component: classMatches[0] };
  }

  const bareMatch = attrText.match(/^([A-Za-z0-9_-]+)/);
  return {
    kind: "open",
    component: bareMatch ? bareMatch[1] : defaultComponent,
  };
}

async function buildTocGroups({
  app,
  tocPath = "Table of Contents.md",
  contentsPrefix = "contents/",
  defaultComponent = "narrative",
  ungroupedHeading = "Ungrouped",
} = {}) {
  if (!app) throw new Error("buildTocGroups requires app.");

  const tocFile = app.vault.getAbstractFileByPath(tocPath);

  if (!tocFile?.path) {
    return {
      tocFile: null,
      groups: [],
      linkedContentPaths: new Set(),
      badTocLinks: [],
    };
  }

  const text = await app.vault.cachedRead(tocFile);
  const lines = String(text || "").split(/\r?\n/);
  const headingStack = [];
  const componentStack = [];
  const groups = [];
  const groupMap = new Map();
  const linkedContentPaths = new Set();
  const badTocLinks = [];
  const badTocKeys = new Set();

  function ensureGroup(name) {
    if (!groupMap.has(name)) {
      const group = { heading: name, items: [] };
      groupMap.set(name, group);
      groups.push(group);
    }

    return groupMap.get(name);
  }

  function rememberBadTocLink({ heading, linkText, status, targetPath }) {
    const key = `${heading}::${linkText}::${status}::${targetPath ?? ""}`;
    if (badTocKeys.has(key)) return;

    badTocKeys.add(key);
    badTocLinks.push({
      heading,
      linkText,
      status,
      targetPath,
      targetText: targetPath ?? "No matching file",
    });
  }

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);

    if (headingMatch) {
      const level = headingMatch[1].length;
      const title = headingMatch[2].trim();
      headingStack.length = level - 1;
      headingStack[level - 1] = title;
      continue;
    }

    const fence = parseFenceComponent(line, { defaultComponent });

    if (fence) {
      if (fence.kind === "close") {
        if (componentStack.length > 0) componentStack.pop();
      } else {
        componentStack.push(fence.component || defaultComponent);
      }
      continue;
    }

    const heading = headingStack.filter(Boolean).join(" › ") || ungroupedHeading;
    const group = ensureGroup(heading);
    const currentComponent = componentStack.at(-1) || defaultComponent;

    for (const link of parseWikilinks(line)) {
      const dest = app.metadataCache.getFirstLinkpathDest(link.target, tocPath);

      if (!dest) {
        rememberBadTocLink({
          heading,
          linkText: link.raw,
          status: "Unresolved",
          targetPath: null,
        });
        continue;
      }

      if (!isMarkdownPathUnder(dest.path, contentsPrefix)) {
        rememberBadTocLink({
          heading,
          linkText: link.raw,
          status: "Resolves outside contents",
          targetPath: dest.path,
        });
        continue;
      }

      if (!isPublicVaultPath(dest.path)) {
        rememberBadTocLink({
          heading,
          linkText: link.raw,
          status: "Resolves inside _* folder",
          targetPath: dest.path,
        });
        continue;
      }

      const slug = getSlug(app, dest);

      if (!slug) {
        rememberBadTocLink({
          heading,
          linkText: link.raw,
          status: "Linked content file has no slug",
          targetPath: dest.path,
        });
        continue;
      }

      linkedContentPaths.add(dest.path);

      if (group.items.some(item => item.path === dest.path)) continue;

      group.items.push({
        id: `${heading}::${slug}`,
        heading,
        slug,
        path: dest.path,
        name: dest.basename,
        basename: dest.basename,
        folder: getFolderPath(dest.path),
        component: currentComponent,
      });
    }
  }

  return {
    tocFile,
    groups: groups.filter(group => group.items.length > 0),
    linkedContentPaths,
    badTocLinks,
  };
}

function findUnlinkedContentFiles({ app, linkedContentPaths, contentsPrefix = "contents/" } = {}) {
  if (!app) throw new Error("findUnlinkedContentFiles requires app.");
  const linked = linkedContentPaths ?? new Set();

  return app.vault
    .getMarkdownFiles()
    .filter(file => isPublicSluggedFile(app, file, { contentsPrefix }))
    .filter(file => !linked.has(file.path))
    .sort((a, b) => a.path.localeCompare(b.path));
}

function serializeTocRow(row, index) {
  return {
    order: index + 1,
    id: row.id,
    slug: row.slug,
    heading: row.heading,
    tocHeading: row.heading,
    path: row.path,
    name: row.name,
    basename: row.basename ?? row.name,
    folder: row.folder,
    component: row.component,
    tocComponent: row.component,
  };
}

function buildManifestText(rows) {
  const lines = [];
  let currentHeading = null;

  for (const row of rows) {
    if (row.heading && row.heading !== currentHeading) {
      if (lines.at(-1) !== "") lines.push("");
      lines.push(`## ${row.heading}`);
      lines.push("");
      currentHeading = row.heading;
    }

    lines.push(row.path);
  }

  return lines.join("\n").replace(/\n+$/g, "\n");
}

function tocSavedSelectionExtras({ rows, tocPath }) {
  const headings = [];
  const seenHeadings = new Set();
  const tocComponents = [];
  const seenComponents = new Set();
  const folders = [];
  const seenFolders = new Set();

  for (const row of rows) {
    if (row.heading && !seenHeadings.has(row.heading)) {
      seenHeadings.add(row.heading);
      headings.push(row.heading);
    }

    if (row.component && !seenComponents.has(row.component)) {
      seenComponents.add(row.component);
      tocComponents.push(row.component);
    }

    if (row.folder && !seenFolders.has(row.folder)) {
      seenFolders.add(row.folder);
      folders.push(row.folder);
    }
  }

  return {
    tocPath,
    headings,
    tocComponents,
    folders,
    manifestText: buildManifestText(rows),
  };
}

module.exports = {
  isMarkdownPathUnder,
  getSlug,
  isPublicSluggedFile,
  parseFenceComponent,
  buildTocGroups,
  findUnlinkedContentFiles,
  serializeTocRow,
  buildManifestText,
  tocSavedSelectionExtras,
};
