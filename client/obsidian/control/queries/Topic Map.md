```dataviewjs
const SOURCE = '"topics"';

const pages = dv.pages(SOURCE)
  .sort(page => page.file.path, "asc")
  .array();

const root = dv.container;
root.innerHTML = "";

function stripTrailingHashes(text) {
  return text.replace(/\s+#+\s*$/, "").trim();
}

function stripMarkdownFormatting(text) {
  return text
    .replace(/\[\[([^\]|#]+#)?([^\]|]+)(\|([^\]]+))?\]\]/g, (_, _target, heading, _aliasPart, alias) => alias ?? heading)
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`~]/g, "")
    .trim();
}

function extractHeadingOnLine(line) {
  const match = line.match(/^#\s+(.+?)\s*$/);
  if (!match) return null;

  const heading = stripMarkdownFormatting(stripTrailingHashes(match[1]));
  return heading || null;
}

function extractHeadingOnNextLine(previousLine, line) {
  if (!/^=+\s*$/.test(line)) return null;
  const heading = stripMarkdownFormatting(previousLine.trim());
  return heading || null;
}

function extractHeading1s(markdown) {
  const lines = markdown.split(/\r?\n/);
  const headings = [];
  let inFence = false;
  let previousLine = "";

  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      previousLine = line;
      continue;
    }

    if (inFence) {
      previousLine = line;
      continue;
    }

    const atxHeading = extractHeadingOnLine(line);
    if (atxHeading) {
      headings.push(atxHeading);
      previousLine = line;
      continue;
    }

    const setextHeading = extractHeadingOnNextLine(previousLine, line);
    if (setextHeading) {
      headings.push(setextHeading);
    }

    previousLine = line;
  }

  return headings;
}

function makeHeadingTarget(page, heading) {
  return `${page.file.path}#${heading}`;
}

function makeFileTarget(page) {
  return page.file.path;
}

function makeWikilink(page, heading) {
  const basename = page.file.basename ?? page.file.name.replace(/\.md$/i, "");
  return `[[${basename}#${heading}]]`;
}

function makeInternalLink(target, label) {
  const link = document.createElement("a");
  link.textContent = label;
  link.href = target;
  link.className = "internal-link";
  link.setAttribute("data-href", target);

  link.addEventListener("click", event => {
    event.preventDefault();
    app.workspace.openLinkText(
      target,
      dv.current().file.path,
      event.ctrlKey || event.metaKey
    );
  });

  return link;
}

function makeHeadingLink(page, heading) {
  return makeInternalLink(makeHeadingTarget(page, heading), heading);
}

function makeFileLink(page) {
  return makeInternalLink(makeFileTarget(page), page.file.name);
}

function makeDisplayId(page) {
  return `topic-map-${page.file.path}`
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function makeDisplayJumpLink(record) {
  const link = document.createElement("a");
  link.textContent = record.page.file.name;
  link.href = `#${record.displayId}`;

  link.addEventListener("click", event => {
    event.preventDefault();

    const target = root.querySelector(`#${CSS.escape(record.displayId)}`);
    if (!target) return;

    target.scrollIntoView({ behavior: "smooth", block: "start" });
    target.focus({ preventScroll: true });
  });

  return link;
}

function makeCopyButton(page, heading) {
  const button = document.createElement("button");
  button.textContent = "Copy";
  button.title = "Copy simple wikilink to heading";

  button.addEventListener("click", async () => {
    const wikilink = makeWikilink(page, heading);

    try {
      await navigator.clipboard.writeText(wikilink);
      const oldText = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = oldText;
      }, 1200);
    } catch (error) {
      console.error("Could not copy wikilink", error);
      new Notice(`Could not copy: ${wikilink}`);
    }
  });

  return button;
}

function makeHeadingRow(page, heading) {
  const item = document.createElement("li");
  item.style.display = "flex";
  item.style.alignItems = "center";
  item.style.gap = "0.5rem";
  item.style.margin = "0.2rem 0";

  item.appendChild(makeHeadingLink(page, heading));
  item.appendChild(makeCopyButton(page, heading));

  return item;
}

function makeFileHeading(page) {
  const heading = document.createElement("h1");
  heading.appendChild(makeFileLink(page));
  return heading;
}

function makeLayout() {
  const layout = document.createElement("div");
  layout.style.display = "flex";
  layout.style.alignItems = "flex-start";
  layout.style.gap = "1.5rem";

  const sidebar = document.createElement("aside");
  sidebar.style.flex = "0 0 16rem";
  sidebar.style.maxWidth = "16rem";
  sidebar.style.position = "sticky";
  sidebar.style.top = "1rem";
  sidebar.style.maxHeight = "calc(100vh - 2rem)";
  sidebar.style.overflow = "auto";
  sidebar.style.borderRight = "1px solid var(--background-modifier-border)";
  sidebar.style.paddingRight = "1rem";

  const main = document.createElement("section");
  main.style.flex = "1 1 auto";
  main.style.minWidth = "0";

  layout.appendChild(sidebar);
  layout.appendChild(main);
  root.appendChild(layout);

  return { sidebar, main };
}

function renderSidebar(sidebar, records) {
  const title = document.createElement("h2");
  title.textContent = "File Index";
  sidebar.appendChild(title);

  const list = document.createElement("ul");
  list.style.paddingLeft = "1.1rem";

  for (const record of records) {
    const item = document.createElement("li");
    item.style.margin = "0.25rem 0";
    item.appendChild(makeDisplayJumpLink(record));
    list.appendChild(item);
  }

  sidebar.appendChild(list);
}

function renderTopicMap(main, records) {
  for (const record of records) {
    const fileHeading = makeFileHeading(record.page);
    fileHeading.id = record.displayId;
    fileHeading.tabIndex = -1;
    main.appendChild(fileHeading);

    if (record.headings.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "No Heading 1 sections found.";
      empty.style.fontStyle = "italic";
      main.appendChild(empty);
      continue;
    }

    const list = document.createElement("ul");

    for (const heading of record.headings) {
      list.appendChild(makeHeadingRow(record.page, heading));
    }

    main.appendChild(list);
  }
}

async function collectRecords() {
  const records = [];

  for (const page of pages) {
    const file = app.vault.getAbstractFileByPath(page.file.path);
    if (!file) continue;

    const markdown = await app.vault.cachedRead(file);
    records.push({
      page,
      displayId: makeDisplayId(page),
      headings: extractHeading1s(markdown),
    });
  }

  return records;
}

async function renderTopicMapWithIndex() {
  if (pages.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No files found in topics.";
    empty.style.fontStyle = "italic";
    root.appendChild(empty);
    return;
  }

  const records = await collectRecords();
  const { sidebar, main } = makeLayout();

  renderSidebar(sidebar, records);
  renderTopicMap(main, records);
}

await renderTopicMapWithIndex();
```
