# Vault Dashboard

> [!summary] Control surface
> Use this page as the F3 cockpit for the current vault: open queries and panels, review slug coverage, and find public files that still need slugs.

```dataviewjs
const CONFIG = {
  queryFolder: "_control/queries",
  panelFolder: "_control/panels",
  missingSlugLimit: 100,
  excludedFiles: new Set(["Table of Contents.md"])
};

const sourcePath = app.workspace.getActiveFile()?.path || "_control/Dashboard.md";

function folderPrefix(folder) {
  return `${String(folder).replace(/\/+$/, "")}/`;
}

function isInside(path, folder) {
  return String(path).startsWith(folderPrefix(folder));
}

function isPrivatePath(path) {
  return String(path)
    .split("/")
    .slice(0, -1)
    .some(segment => segment.startsWith("_"));
}

function displayName(file) {
  return file.basename;
}

function slugPrefix(slug) {
  const value = String(slug || "").trim();
  if (!value) return null;

  const match = value.match(/^([^.:-]+)[.:-]/);
  return match ? match[1] : value;
}

function markdownFilesIn(folder) {
  return app.vault.getMarkdownFiles()
    .filter(file => isInside(file.path, folder))
    .sort((a, b) => displayName(a).localeCompare(displayName(b)));
}

async function openControlFile(linkTarget) {
  const file =
    typeof linkTarget === "string"
      ? app.metadataCache.getFirstLinkpathDest(linkTarget, sourcePath)
      : linkTarget;

  if (!file?.path) {
    throw new Error(`Control file not found: ${String(linkTarget)}`);
  }

  const existingLeaf = app.workspace.getLeavesOfType("markdown").find(
    leaf => leaf.view?.file?.path === file.path
  );

  if (existingLeaf) {
    await app.workspace.revealLeaf(existingLeaf);
    return;
  }

  const leaf = app.workspace.getLeaf("tab");
  await leaf.openFile(file);
  await app.workspace.revealLeaf(leaf);
}

const queries = markdownFilesIn(CONFIG.queryFolder);
const panels = markdownFilesIn(CONFIG.panelFolder);

const publicFiles = app.vault.getMarkdownFiles().filter(file =>
  !isPrivatePath(file.path) &&
  !CONFIG.excludedFiles.has(file.name)
);

const prefixCounts = new Map();
const missingSlugs = [];

for (const file of publicFiles) {
  const frontmatter = app.metadataCache.getFileCache(file)?.frontmatter;
  const slug = String(frontmatter?.slug || "").trim();

  if (!slug) {
    missingSlugs.push(file);
    continue;
  }

  const prefix = slugPrefix(slug);
  prefixCounts.set(prefix, (prefixCounts.get(prefix) || 0) + 1);
}

missingSlugs.sort((a, b) => a.path.localeCompare(b.path));

const prefixRows = [...prefixCounts.entries()]
  .sort(([a], [b]) => a.localeCompare(b))
  .map(([prefix, count]) => [prefix, count]);

function renderLinkList(heading, files) {
  dv.header(2, heading);

  if (!files.length) {
    dv.paragraph("_None found._");
    return;
  }

  dv.list(files.map(file => dv.fileLink(file.path, false, displayName(file))));
}

renderLinkList("Queries", queries);
renderLinkList("Panels", panels);

dv.header(2, "Files by slug prefix");
if (prefixRows.length) {
  dv.table(["Prefix", "Files"], prefixRows);
} else {
  dv.paragraph("_No slugs found outside private folders._");
}

dv.header(2, "Files without slugs");
if (!missingSlugs.length) {
  dv.paragraph("All Markdown files outside `_` folders have slugs.");
} else {
  const shown = missingSlugs.slice(0, CONFIG.missingSlugLimit);
  dv.paragraph(
    `${missingSlugs.length} Markdown file${missingSlugs.length === 1 ? "" : "s"} outside \`_\` folders ${missingSlugs.length === 1 ? "has" : "have"} no slug.`
  );
  dv.list(shown.map(file => dv.fileLink(file.path)));

  if (shown.length < missingSlugs.length) {
    dv.paragraph(`Showing the first ${shown.length}.`);
  }
}

const dashboardContainer = dv.container;

if (!dashboardContainer.dataset.controlOpenGuard) {
  dashboardContainer.dataset.controlOpenGuard = "true";

  dashboardContainer.addEventListener("click", async event => {
    const link = event.target.closest("a.internal-link");
    if (!link || !dashboardContainer.contains(link)) return;

    const linkTarget = link.dataset.href || link.getAttribute("href") || "";
    const file = app.metadataCache.getFirstLinkpathDest(linkTarget, sourcePath);

    if (
      !file?.path ||
      (!isInside(file.path, CONFIG.queryFolder) &&
       !isInside(file.path, CONFIG.panelFolder))
    ) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    await openControlFile(file);
  });
}
```
