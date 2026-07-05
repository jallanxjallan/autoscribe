function makeContentStatusView({
  app,
  dv,
  nodeRequire,
  queryPath,
  vaultName,
  config,
  renderSelectionQuery,
}) {
  const CONFIG = {
    tempRoot: "",
    debug: false,

    defaultClass: "—",
    defaultStatus: "—",
    defaultStage: "—",
    defaultRepoState: "—",
    defaultSlugPrefix: "—",

    slugPrefixes: ["cnt", "img"],

    excludePaths: [
      ".obsidian",
      ".trash",
      ".autoscribe",
    ],

    ...(config || {}),
  };

  const fs = nodeRequire("fs");
  const pathMod = nodeRequire("path");
  const childProcess = nodeRequire("child_process");

  const vaultBasePath =
    app.vault.adapter.getBasePath?.() ||
    app.vault.adapter.basePath;

  function asText(value, fallback = "") {
    if (value == null) return fallback;
    if (Array.isArray(value)) return value.map(v => String(v)).join(", ");
    const text = String(value).trim();
    return text || fallback;
  }

  function normalizePath(path) {
    return String(path || "")
      .replace(/\\/g, "/")
      .replace(/^\/+/, "");
  }

  function isUnderscoreFolder(path) {
    return normalizePath(path)
      .split("/")
      .slice(0, -1)
      .some(part => part.startsWith("_"));
  }

  function isExcludedPath(path) {
    const clean = normalizePath(path);

    if (isUnderscoreFolder(clean)) return true;

    return CONFIG.excludePaths.some(prefix => {
      const cleanPrefix = normalizePath(prefix).replace(/\/+$/, "");
      return clean === cleanPrefix || clean.startsWith(`${cleanPrefix}/`);
    });
  }

  function normalizeSlug(slug) {
    return asText(slug).toLowerCase().trim();
  }

  function configuredSlugPrefixes() {
    return CONFIG.slugPrefixes
      .map(prefix => String(prefix || "").toLowerCase().trim().replace(/[.\-_/|:]+$/, ""))
      .filter(Boolean);
  }

  function slugHead(slug) {
    const clean = normalizeSlug(slug);
    return clean.split(/[.\-_/|:]/)[0] || "";
  }

  function slugPrefix(slug) {
    const head = slugHead(slug);
    if (!head) return CONFIG.defaultSlugPrefix;
    return configuredSlugPrefixes().includes(head) ? head : CONFIG.defaultSlugPrefix;
  }

  function slugMatchesCriteria(slug) {
    const head = slugHead(slug);
    if (!head) return false;
    return configuredSlugPrefixes().includes(head);
  }

  function titleForPage(page) {
    return (
      asText(page.title) ||
      asText(page.file?.name) ||
      asText(page.file?.path)
    );
  }

  function sluggedPageForPath(path) {
    const clean = normalizePath(path);
    if (isExcludedPath(clean)) return null;

    const page = dv.page(clean);
    if (!page) return null;

    const slug = asText(page.slug);
    if (!slug) return null;
    if (!slugMatchesCriteria(slug)) return null;

    return page;
  }

  function allSluggedPages() {
    return app.vault.getMarkdownFiles()
      .map(file => sluggedPageForPath(file.path))
      .filter(Boolean);
  }

  function runGit(argv, { cwd = vaultBasePath, check = false } = {}) {
    const proc = childProcess.spawnSync(
      "git",
      argv,
      {
        cwd,
        encoding: "utf8",
      }
    );

    if (check && proc.status !== 0) {
      const detail = String(proc.stderr || proc.stdout || "git failed").trim();
      throw new Error(`git ${argv.join(" ")} failed: ${detail}`);
    }

    return proc;
  }

  function gitRepoRoot() {
    const proc = runGit(["rev-parse", "--show-toplevel"]);
    if (proc.status !== 0) return "";
    return String(proc.stdout || "").trim();
  }

  const REPO_ROOT = gitRepoRoot();

  function pathRelativeToVaultFromRepoStatusPath(statusPath) {
    if (!REPO_ROOT) return normalizePath(statusPath);

    const absolute = pathMod.resolve(REPO_ROOT, statusPath);
    const relativeToVault = pathMod.relative(vaultBasePath, absolute);

    if (!relativeToVault || relativeToVault.startsWith("..")) {
      return "";
    }

    return normalizePath(relativeToVault);
  }

  function gitStatusMap() {
    const proc = runGit(["status", "--porcelain=v1", "--untracked-files=all"]);
    if (proc.status !== 0) return new Map();

    const map = new Map();

    for (const raw of String(proc.stdout || "").split(/\r?\n/)) {
      if (!raw.trim()) continue;
      if (raw.length < 4) continue;

      const indexStatus = raw[0];
      const worktreeStatus = raw[1];
      const payload = raw.slice(3);
      const rawPath = payload.includes(" -> ")
        ? payload.split(" -> ").pop()
        : payload;

      const cleanPath = pathRelativeToVaultFromRepoStatusPath(rawPath);
      if (!cleanPath) continue;

      if (indexStatus === "?" && worktreeStatus === "?") {
        map.set(cleanPath, "new");
      } else {
        map.set(cleanPath, "editing");
      }
    }

    return map;
  }

  const GIT_STATUS = gitStatusMap();
  const LATEST_COMMIT_CACHE = new Map();
  const TAGS_AT_COMMIT_CACHE = new Map();
  const LATEST_SUBJECT_CACHE = new Map();

  function markerNameForPath(path) {
    return normalizePath(path).replace(/[\\/]/g, "__");
  }

  function markerExists(kind, path) {
    const markerPath = pathMod.join(
      vaultBasePath,
      ".autoscribe",
      "workflow",
      kind,
      `${markerNameForPath(path)}.json`
    );
    return fs.existsSync(markerPath);
  }

  function latestCommitForPath(path) {
    const clean = normalizePath(path);
    if (LATEST_COMMIT_CACHE.has(clean)) return LATEST_COMMIT_CACHE.get(clean);

    const proc = runGit(["log", "-1", "--pretty=%H", "--", clean]);
    const commit = proc.status === 0 ? String(proc.stdout || "").trim() : "";

    LATEST_COMMIT_CACHE.set(clean, commit);
    return commit;
  }

  function latestSubjectForPath(path) {
    const clean = normalizePath(path);
    if (LATEST_SUBJECT_CACHE.has(clean)) return LATEST_SUBJECT_CACHE.get(clean);

    const proc = runGit(["log", "-1", "--pretty=%s", "--", clean]);
    const subject = proc.status === 0 ? String(proc.stdout || "").trim() : "";

    LATEST_SUBJECT_CACHE.set(clean, subject);
    return subject;
  }

  function tagsAtCommit(commit) {
    if (!commit) return [];
    if (TAGS_AT_COMMIT_CACHE.has(commit)) return TAGS_AT_COMMIT_CACHE.get(commit);

    const proc = runGit(["tag", "--points-at", commit]);
    const tags = proc.status === 0
      ? String(proc.stdout || "")
          .split(/\r?\n/)
          .map(line => line.trim())
          .filter(Boolean)
      : [];

    TAGS_AT_COMMIT_CACHE.set(commit, tags);
    return tags;
  }

  function isPipelineTag(tag) {
    const clean = String(tag || "").trim().toLowerCase();
    return (
      /^autoscribe[\/._-]in-flight\b/.test(clean) ||
      /^in-flight[\/._-]/.test(clean) ||
      /^pipeline[\/._-]/.test(clean)
    );
  }

  function hasPipelineTag(path) {
    const commit = latestCommitForPath(path);
    return tagsAtCommit(commit).some(isPipelineTag);
  }

  function hasPipelineMarker(path) {
    return markerExists("in-flight", path);
  }

  function hasConflictMarker(path) {
    return markerExists("conflicts", path);
  }

  function latestCommitMarksWritten(path) {
    return /^autoscribe: writeback\b/.test(latestSubjectForPath(path));
  }

  function repoStateForPath(path) {
    const clean = normalizePath(path);

    if (hasConflictMarker(clean)) return "conflicted";

    const gitState = GIT_STATUS.get(clean);
    if (gitState === "new") return "new";
    if (gitState === "editing") return "editing";

    if (hasPipelineMarker(clean) || hasPipelineTag(clean)) return "in-flight";
    if (latestCommitMarksWritten(clean)) return "written";

    return "committed";
  }

  function statusRowFromPage(page) {
    const path = normalizePath(page.file.path);
    const slug = asText(page.slug);
    const title = titleForPage(page);

    return {
      id: slug,
      selection_key: slug,

      path,
      name: title,
      title,
      slug,

      slug_prefix: slugPrefix(slug),

      class: asText(page.class, CONFIG.defaultClass),
      status: asText(page.status, CONFIG.defaultStatus),
      stage: asText(page.stage, CONFIG.defaultStage),
      repo_state: repoStateForPath(path),
    };
  }

  function alphaCompare(a, b) {
    return String(a.title || a.name || a.path).localeCompare(
      String(b.title || b.name || b.path),
      undefined,
      { sensitivity: "base" }
    );
  }

  function buildRows() {
    return allSluggedPages().map(statusRowFromPage);
  }

  function serializeStatusRow(row) {
    return {
      selection_key: row.slug,
      slug: row.slug,
      slug_prefix: row.slug_prefix,
      title: row.title,
      path: row.path,
      class: row.class,
      status: row.status,
      stage: row.stage,
      repo_state: row.repo_state,
    };
  }

  function savedSelectionExtras({ rows }) {
    return {
      ordering: "content-status",
      displayed_count: rows.length,
      filters: ["class", "status", "stage", "repo_state"],
      sort_modes: ["title"],
      slug_prefixes: CONFIG.slugPrefixes,
    };
  }

  function sortRows(rows, mode) {
    const copy = [...rows];

    if (mode === "title-desc") {
      return copy.sort((a, b) => alphaCompare(b, a));
    }

    return copy.sort(alphaCompare);
  }

  function setTriState(box, checkedCount, totalCount) {
    box.checked = totalCount > 0 && checkedCount === totalCount;
    box.indeterminate = checkedCount > 0 && checkedCount < totalCount;
  }

  function renderGroupedResults(parent, displayedRows, api) {
    const sortedRows = sortRows(displayedRows, api.model.sortMode || "title-asc");

    const section = parent.createDiv();
    section.style.marginBottom = "1.5em";

    const headingRow = section.createDiv();
    headingRow.style.display = "flex";
    headingRow.style.alignItems = "center";
    headingRow.style.gap = "0.6em";
    headingRow.style.marginBottom = "0.5em";

    const checkedCount = sortedRows.filter(row => api.model.selectedKeys.has(row.slug)).length;

    const groupBox = headingRow.createEl("input", { type: "checkbox" });
    setTriState(groupBox, checkedCount, sortedRows.length);
    groupBox.onchange = async () => {
      for (const row of sortedRows) {
        if (groupBox.checked) api.model.selectedKeys.add(row.slug);
        else api.model.selectedKeys.delete(row.slug);
      }

      await api.saveCurrentState({ quiet: true, action: "selection" });
      api.render();
    };

    headingRow.createEl("strong", { text: "Content Status" });

    const countText = headingRow.createEl("span");
    countText.style.opacity = "0.75";
    countText.setText(`(${checkedCount}/${sortedRows.length})`);

    const tableWrap = section.createDiv();
    tableWrap.style.overflowX = "auto";

    const table = tableWrap.createEl("table");
    table.classList.add("dataview", "table-view-table");
    table.style.width = "100%";

    const thead = table.createEl("thead");
    const headRow = thead.createEl("tr");

    [
      "",
      "Title",
      "Class",
      "Status",
      "Stage",
      "Repo",
    ].forEach(text => headRow.createEl("th", { text }));

    const tbody = table.createEl("tbody");

    for (const row of sortedRows) {
      const tr = tbody.createEl("tr");

      const selectCell = tr.createEl("td");
      const itemBox = selectCell.createEl("input", { type: "checkbox" });
      itemBox.checked = api.model.selectedKeys.has(row.slug);
      itemBox.onchange = async () => {
        if (itemBox.checked) api.model.selectedKeys.add(row.slug);
        else api.model.selectedKeys.delete(row.slug);

        await api.saveCurrentState({ quiet: true, action: "selection" });
        api.render();
      };

      const noteCell = tr.createEl("td");
      api.createInternalLink(noteCell, row.path, row.title);

      tr.createEl("td", { text: row.class });
      tr.createEl("td", { text: row.status });
      tr.createEl("td", { text: row.stage });
      tr.createEl("td", { text: row.repo_state });
    }
  }

  async function saveSelectionManifest(api) {
    await api.saveDataviewSelection({
      operation: "content-status",
      queryName: "Content Status",
      namespace: "content-status",
      selectionSource: "content-status",
      selectionKind: "slug",
      selectionKey: "slug",
      serializeRow: serializeStatusRow,
      options: {
        filters: ["class", "status", "stage", "repo_state"],
        sort_modes: ["title"],
        slug_prefixes: CONFIG.slugPrefixes,
      },
      savedSelectionExtras({ rows }) {
        return savedSelectionExtras({ rows });
      }
    });
  }

  async function render() {
    const rows = buildRows();

    if (!rows.length) {
      dv.container.innerHTML = "";
      dv.paragraph(`No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`);
      return;
    }

    await renderSelectionQuery({
      app,
      dv,
      nodeRequire,

      title: "Content Status",
      namespace: "content-status",
      bridgeName: "__contentStatusSelection",

      vaultName,
      queryPath,
      stateVersion: 1,
      tempRoot: CONFIG.tempRoot,

      rows,
      columns: [],

      filterFields: [
        { key: "class", title: "Class" },
        { key: "status", title: "Status" },
        { key: "stage", title: "Stage" },
        { key: "repo_state", title: "Repo" },
      ],

      sortModes: [
        ["title-asc", "Title A–Z"],
        ["title-desc", "Title Z–A"],
      ],

      defaultSortMode: "title-asc",

      selectionKind: "slug",
      selectionKey: "slug",
      serializeRow: serializeStatusRow,
      savedSelectionExtras({ rows }) {
        return savedSelectionExtras({ rows });
      },

      emptyMessage: `No Markdown files matched slug prefixes ${CONFIG.slugPrefixes.join(", ")}.`,
      noMatchesMessage: "No matching content-status rows.",

      summaryText({ displayedRows, selectedRows }) {
        return `${displayedRows.length} content file(s) displayed · ${selectedRows.length} checked`;
      },

      renderActions(parent, api) {
        const saveButton = parent.createEl("button", { text: "Save selection manifest" });
        saveButton.onclick = async () => {
          await saveSelectionManifest(api);
        };
      },

      renderResults: renderGroupedResults,

      debug: CONFIG.debug,
    });
  }

  return { render };
}

module.exports = {
  makeContentStatusView,
};
