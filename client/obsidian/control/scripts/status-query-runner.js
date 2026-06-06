function normalizeList(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
}

function normalizeConfig(config = {}) {
  return {
    slugPrefixes: normalizeList(config.slugPrefixes),
    excludePaths: normalizeList(config.excludePaths),
    tempRoot: String(config.tempRoot || ""),
    debug: Boolean(config.debug),
    autoscribeRoot: String(config.autoscribeRoot || "_autoscribe").replace(/^\/+|\/+$/g, ""),
  };
}

function buildRows({ app, statusQuery, scope, config }) {
  const options = {
    prefixes: config.slugPrefixes,
    excludePaths: config.excludePaths,
  };

  if (scope === "autoscribe") {
    if (typeof statusQuery.buildAutoscribeStatusRows !== "function") {
      throw new Error(
        "slug-status-query.js must export buildAutoscribeStatusRows(app, options)."
      );
    }

    return statusQuery.buildAutoscribeStatusRows(app, {
      ...options,
      root: config.autoscribeRoot,
    });
  }

  if (typeof statusQuery.buildPublicStatusRows !== "function") {
    throw new Error(
      "slug-status-query.js must export buildPublicStatusRows(app, options)."
    );
  }

  return statusQuery.buildPublicStatusRows(app, options);
}

function defaultSummaryLabel(scope, config) {
  if (scope === "autoscribe") return config.autoscribeRoot;
  if (scope === "control") return "control";
  return "public";
}

function manifestOptions({ scope, config }) {
  const options = {
    selection_kind: "slug",
    selection_key: "slug",
    slug_prefixes: config.slugPrefixes,
    exclude_paths: config.excludePaths,
    scope,
  };

  if (scope === "autoscribe") {
    options.autoscribe_root = config.autoscribeRoot;
  }

  return options;
}

async function renderStatusQuery({
  app,
  dv,
  runtime,
  config: rawConfig = {},

  scope,
  title,
  namespace,
  bridgeName,
  operation,
  queryName,

  emptyMessage,
  noMatchesMessage,
  stateVersion = 3,
}) {
  const config = normalizeConfig(rawConfig);
  const { loader, queryPath, vaultName } = runtime;

  const fs = runtime.nodeRequire("node:fs");
  const path = runtime.nodeRequire("node:path");

  const { renderSelectionQuery } = loader.requireControl(
    "scripts/lib/selection-query.js"
  );

  const {
    getVaultKeyFromRoot,
    getManifestPathFromVaultKey,
  } = loader.requireControl("scripts/lib/operation-manifest.js");

  const statusQuery = loader.requireControl("scripts/lib/slug-status-query.js");

  const {
    STATUS_FILTER_FIELDS,
    STATUS_SORT_MODES,
    sortStatusRows,
    serializeStatusRow,
    statusColumns,
    renderDuplicateSlugWarning,
  } = statusQuery;

  const { slugIndex, rows } = buildRows({
    app,
    statusQuery,
    scope,
    config,
  });

  async function saveSelectionManifest(api) {
    const selectedRows = api.getSelectedRows();
    const items = selectedRows.map((row, index) =>
      serializeStatusRow(row, index)
    );

    const timestamp = new Date().toISOString();

    const vaultRoot =
      app.vault.adapter.getBasePath?.() ||
      app.vault.adapter.basePath;

    const vaultKey = getVaultKeyFromRoot(vaultRoot);

    const manifestPath = getManifestPathFromVaultKey({
      vaultKey,
      operation,
    });

    const manifest = {
      type: "operation_manifest",
      recordType: "operation_manifest",

      timestamp,
      savedAt: timestamp,
      saved_at: timestamp,

      operation,
      queryName,
      namespace,

      vaultName,
      vault: vaultName,
      vaultRoot,
      vaultKey,
      queryPath,

      options: {
        selection_source: namespace,
        ...manifestOptions({ scope, config }),
      },

      count: items.length,
      items,
    };

    fs.mkdirSync(path.dirname(manifestPath), { recursive: true });

    fs.writeFileSync(
      manifestPath,
      `${JSON.stringify(manifest, null, 2)}\n`,
      "utf8"
    );

    await api.saveCurrentState({ quiet: true, action: "manifest" });

    api.notify(`Saved ${items.length} selected item(s) to ${manifestPath}`);
  }

  await renderSelectionQuery({
    app,
    dv,
    nodeRequire: runtime.nodeRequire,

    title,
    namespace,
    bridgeName,

    vaultName,
    queryPath,
    stateVersion,
    tempRoot: config.tempRoot,

    rows,
    columns: statusColumns(),
    filterFields: STATUS_FILTER_FIELDS,
    sortModes: STATUS_SORT_MODES,
    defaultSortMode: "slug",
    sortRows: sortStatusRows,

    selectionKind: "slug",
    selectionKey: "slug",
    serializeRow: serializeStatusRow,

    emptyMessage,
    noMatchesMessage,

    summaryText({ rows, displayedRows, selectedRows }) {
      const label = defaultSummaryLabel(scope, config);
      return `${rows.length} ${label} slugged files indexed · ${displayedRows.length} displayed · ${selectedRows.length} checked`;
    },

    renderSummaryExtras(parent) {
      renderDuplicateSlugWarning(parent, slugIndex.duplicateSlugs);
    },

    renderActions(parent, api) {
      const saveButton = parent.createEl("button", {
        text: "Save selection manifest",
      });

      saveButton.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();

        const originalText = saveButton.textContent;
        saveButton.disabled = true;
        saveButton.textContent = "Saving…";

        try {
          await saveSelectionManifest(api);
        } catch (error) {
          console.error(`${queryName}: failed to save selection manifest`, error);
          api.notify(`Could not save ${queryName} selection manifest. See console.`);
        } finally {
          saveButton.disabled = false;
          saveButton.textContent = originalText;
        }
      });
    },

    debug: config.debug,
  });
}

module.exports = {
  renderStatusQuery,
};