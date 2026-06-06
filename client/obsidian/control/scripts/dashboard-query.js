function normalizeList(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
}

function normalizeConfig(config = {}) {
  return {
    contentPrefixes: normalizeList(config.contentPrefixes).length
      ? normalizeList(config.contentPrefixes)
      : ["pss", "img", "scn"],

    provisionalPrefix: String(config.provisionalPrefix || "prv").trim(),

    queryFolder: String(config.queryFolder || "_control/queries").replace(/^\/+|\/+$/g, ""),

    selectionDir: String(config.selectionDir || ".autoscribe/selections").replace(/^\/+|\/+$/g, ""),

    recentLimit: Number.isFinite(config.recentLimit) ? config.recentLimit : 20,
    missingSlugLimit: Number.isFinite(config.missingSlugLimit) ? config.missingSlugLimit : 50,
  };
}

function pathSegments(vaultPath) {
  return String(vaultPath || "")
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function isPublicVaultPath(vaultPath) {
  return !pathSegments(vaultPath).some((segment) => segment.startsWith("_"));
}

function isInsideFolder(vaultPath, folderPath) {
  const normalizedVaultPath = String(vaultPath || "").replace(/^\/+/, "");
  const normalizedFolder = String(folderPath || "").replace(/^\/+|\/+$/g, "");

  return (
    normalizedVaultPath === normalizedFolder ||
    normalizedVaultPath.startsWith(`${normalizedFolder}/`)
  );
}

function slugPrefix(slug) {
  if (typeof slug !== "string") return null;

  const prefix = slug.trim().split(".")[0];
  return prefix || null;
}

function fileMtime(file) {
  return file?.stat?.mtime ?? 0;
}

function formatDate(ms) {
  if (!ms) return "";
  return new Date(ms).toLocaleString();
}

function pageLabel(page, file) {
  return page?.label ?? page?.title ?? file?.basename ?? file?.name ?? "";
}

function publicMarkdownFiles(app) {
  return app.vault
    .getMarkdownFiles()
    .filter((file) => isPublicVaultPath(file.path));
}

function publicSlugRows(app, dv) {
  return publicMarkdownFiles(app).map((file) => {
    const page = dv.page(file.path);
    const slug = page?.slug;
    const prefix = slugPrefix(slug);

    return {
      file,
      page,
      slug,
      prefix,
      label: pageLabel(page, file),
      mtime: fileMtime(file),
    };
  });
}

function renderTableOrMessage(dv, headers, rows, emptyMessage) {
  if (!rows.length) {
    dv.paragraph(emptyMessage);
    return;
  }

  dv.table(headers, rows);
}

function queryRows(app, dv, config, currentPath) {
  return app.vault
    .getMarkdownFiles()
    .filter((file) => isInsideFolder(file.path, config.queryFolder))
    .filter((file) => file.path !== currentPath)
    .sort((a, b) => String(a.basename).localeCompare(String(b.basename)))
    .map((file) => [
      dv.fileLink(file.path, false, file.basename),
      file.path,
      formatDate(fileMtime(file)),
    ]);
}

function activeCountRows(app, dv, config) {
  const rows = publicSlugRows(app, dv);

  let content = 0;
  let provisional = 0;
  let otherSlugged = 0;
  let missingSlug = 0;

  const contentPrefixes = new Set(config.contentPrefixes);

  for (const row of rows) {
    if (!row.prefix) {
      missingSlug += 1;
    } else if (contentPrefixes.has(row.prefix)) {
      content += 1;
    } else if (row.prefix === config.provisionalPrefix) {
      provisional += 1;
    } else {
      otherSlugged += 1;
    }
  }

  return [
    ["Public Markdown files", rows.length],
    ["Content notes", content],
    ["Provisional notes", provisional],
    ["Other public slugged notes", otherSlugged],
    ["Missing slug", missingSlug],
  ];
}

function recentContentRows(app, dv, config) {
  const contentPrefixes = new Set(config.contentPrefixes);

  return publicSlugRows(app, dv)
    .filter((row) => contentPrefixes.has(row.prefix))
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, config.recentLimit)
    .map((row) => [
      dv.fileLink(row.file.path, false, row.label),
      row.prefix,
      row.slug,
      formatDate(row.mtime),
    ]);
}

function provisionalRows(app, dv, config) {
  return publicSlugRows(app, dv)
    .filter((row) => row.prefix === config.provisionalPrefix)
    .sort((a, b) => b.mtime - a.mtime)
    .map((row) => [
      dv.fileLink(row.file.path, false, row.label),
      row.slug,
      formatDate(row.mtime),
    ]);
}

function missingSlugRows(app, dv, config) {
  return publicSlugRows(app, dv)
    .filter((row) => typeof row.slug !== "string" || !row.slug.trim())
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, config.missingSlugLimit)
    .map((row) => [
      dv.fileLink(row.file.path, false, row.label),
      formatDate(row.mtime),
    ]);
}

function duplicateSlugRows(app, dv) {
  const seen = new Map();

  for (const row of publicSlugRows(app, dv)) {
    const slug = typeof row.slug === "string" ? row.slug.trim() : "";
    if (!slug) continue;

    if (!seen.has(slug)) {
      seen.set(slug, []);
    }

    seen.get(slug).push(row.file.path);
  }

  const rows = [];

  for (const [slug, paths] of seen.entries()) {
    if (paths.length <= 1) continue;

    rows.push([
      slug,
      paths.map((path) => dv.fileLink(path)),
    ]);
  }

  rows.sort((a, b) => String(a[0]).localeCompare(String(b[0])));

  return rows;
}

function vaultRoot(app) {
  const adapter = app.vault.adapter;

  if (typeof adapter.getBasePath === "function") {
    return adapter.getBasePath();
  }

  return adapter.basePath;
}

function savedSelectionRows(app, dv, nodeRequire, config) {
  if (!nodeRequire) {
    return {
      rows: [],
      message: "Node require is unavailable, so saved selection JSON files cannot be listed here.",
    };
  }

  const fs = nodeRequire("fs");
  const path = nodeRequire("path");

  const selectionDir = path.join(vaultRoot(app), ...pathSegments(config.selectionDir));

  if (!fs.existsSync(selectionDir)) {
    return {
      rows: [],
      message: `No \`${config.selectionDir}\` folder found.`,
    };
  }

  const rows = fs
    .readdirSync(selectionDir, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .filter((entry) => entry.name.endsWith(".json"))
    .map((entry) => {
      const filepath = path.join(selectionDir, entry.name);
      let data = null;

      try {
        data = JSON.parse(fs.readFileSync(filepath, "utf8"));
      } catch (_err) {}

      const stat = fs.statSync(filepath);

      return [
        entry.name,
        data?.label ?? data?.name ?? "",
        Array.isArray(data?.items) ? data.items.length : "",
        formatDate(stat.mtimeMs),
      ];
    })
    .sort((a, b) => String(a[0]).localeCompare(String(b[0])));

  return {
    rows,
    message: "No saved selection files found.",
  };
}

function section(dv, title) {
  dv.header(2, title);
}

async function renderVaultDashboard({ app, dv, runtime, config: rawConfig = {} }) {
  const config = normalizeConfig(rawConfig);
  const currentPath = app.workspace.getActiveFile()?.path || "";
  const nodeRequire = runtime?.nodeRequire;

  section(dv, "Query Library");
  renderTableOrMessage(
    dv,
    ["Query", "Path", "Modified"],
    queryRows(app, dv, config, currentPath),
    "No matching query files found."
  );

  section(dv, "Active Counts");
  dv.table(["Area", "Count"], activeCountRows(app, dv, config));

  section(dv, "Recent Content");
  renderTableOrMessage(
    dv,
    ["File", "Prefix", "Slug", "Modified"],
    recentContentRows(app, dv, config),
    "No recent content notes found."
  );

  section(dv, "Provisional Notes");
  renderTableOrMessage(
    dv,
    ["File", "Slug", "Modified"],
    provisionalRows(app, dv, config),
    "No provisional notes found."
  );

  section(dv, "Saved Selections");
  const saved = savedSelectionRows(app, dv, nodeRequire, config);
  renderTableOrMessage(
    dv,
    ["File", "Label", "Items", "Modified"],
    saved.rows,
    saved.message
  );

  section(dv, "Hygiene: Missing Slugs");
  renderTableOrMessage(
    dv,
    ["File", "Modified"],
    missingSlugRows(app, dv, config),
    "No public Markdown files are missing slugs."
  );

  section(dv, "Hygiene: Duplicate Slugs");
  renderTableOrMessage(
    dv,
    ["Slug", "Files"],
    duplicateSlugRows(app, dv),
    "No duplicate public slugs found."
  );
}

module.exports = {
  renderVaultDashboard,

  // Exposed for quick console/debug checks.
  isPublicVaultPath,
  slugPrefix,
  publicMarkdownFiles,
};