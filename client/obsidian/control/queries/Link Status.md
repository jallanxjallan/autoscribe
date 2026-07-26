```dataviewjs
const CONTENT_FOLDER = "Contents";
const TOC_PATH = "Table of Contents.md";

const normalizePath = (path) =>
  String(path || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");

const isContentFile = (file) =>
  file?.extension === "md" &&
  (
    file.path === CONTENT_FOLDER ||
    file.path.startsWith(`${CONTENT_FOLDER}/`)
  );

const tocFile = app.vault.getAbstractFileByPath(TOC_PATH);

if (!tocFile) {
  dv.paragraph(`**Table of contents not found:** ${TOC_PATH}`);
  return;
}

const contentFiles = app.vault
  .getMarkdownFiles()
  .filter(isContentFile)
  .sort((a, b) => a.path.localeCompare(b.path));

const tocText = await app.vault.read(tocFile);

/*
Matches:

[[File]]
[[File|Label]]
[[File#Heading]]
[[File#Heading|Label]]
![[File]]
*/
const linkPattern = /!?\[\[([^\]]+)\]\]/g;

const tocLinks = [];
let match;

while ((match = linkPattern.exec(tocText)) !== null) {
  const original = match[0];
  const inner = match[1].trim();

  const targetWithHeading = inner
    .split("|", 1)[0]
    .trim();

  const linkpath = targetWithHeading
    .split("#", 1)[0]
    .trim();

  if (!linkpath) continue;

  const destination =
    app.metadataCache.getFirstLinkpathDest(
      linkpath,
      tocFile.path
    );

  tocLinks.push({
    original,
    linkpath,
    destination,
    path: destination
      ? normalizePath(destination.path)
      : null,
  });
}

/*
Only successfully resolved links to Markdown files inside the
configured content folder count as content links.
*/
const resolvedContentLinks = tocLinks.filter(
  (link) => isContentFile(link.destination)
);

const linkedContentPaths = new Set(
  resolvedContentLinks.map((link) => link.path)
);

/* 1. Content files not linked from the TOC */
const missingFromToc = contentFiles.filter(
  (file) => !linkedContentPaths.has(normalizePath(file.path))
);

/* 2. TOC links that do not resolve */
const brokenLinks = tocLinks.filter(
  (link) => !link.destination
);

/* 3. Content files linked more than once */
const linkCounts = new Map();

for (const link of resolvedContentLinks) {
  const current = linkCounts.get(link.path) || {
    file: link.destination,
    count: 0,
    links: [],
  };

  current.count += 1;
  current.links.push(link.original);
  linkCounts.set(link.path, current);
}

const duplicateLinks = [...linkCounts.values()]
  .filter((entry) => entry.count > 1)
  .sort((a, b) => a.file.path.localeCompare(b.file.path));

dv.header(2, "Content files not in TOC");

if (missingFromToc.length) {
  dv.table(
    ["File", "Path"],
    missingFromToc.map((file) => [
      dv.fileLink(file.path),
      file.path,
    ])
  );
} else {
  dv.paragraph("✓ Every content file is linked from the TOC.");
}

dv.header(2, "Broken content links in TOC");

if (brokenLinks.length) {
  dv.table(
    ["Link", "Target"],
    brokenLinks.map((link) => [
      `\`${link.original}\``,
      link.linkpath,
    ])
  );
} else {
  dv.paragraph("✓ No broken links were found in the TOC.");
}

dv.header(2, "Duplicate content links in TOC");

if (duplicateLinks.length) {
  dv.table(
    ["File", "Occurrences", "Links"],
    duplicateLinks.map((entry) => [
      dv.fileLink(entry.file.path),
      entry.count,
      entry.links.map((link) => `\`${link}\``).join("<br>"),
    ])
  );
} else {
  dv.paragraph("✓ No content file is linked more than once.");
}
```