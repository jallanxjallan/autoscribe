const { notify } = require("../scripts/lib/notify");
function nodeRequire(name) {
  if (typeof require === "function") return require(name);
  if (typeof window !== "undefined" && window.require) return window.require(name);
  throw new Error(`Node module unavailable: ${name}`);
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;

  if (typeof adapter?.getBasePath === "function") {
    return adapter.getBasePath();
  }

  if (adapter?.basePath) {
    return adapter.basePath;
  }

  throw new Error("Could not determine vault base path.");
}

function requireFromVault(app, vaultRelativePath) {
  const path = nodeRequire("path");
  const fullPath = path.join(getVaultBasePath(app), vaultRelativePath);

  // Helpful during active development.
  if (nodeRequire.cache?.[fullPath]) {
    delete nodeRequire.cache[fullPath];
  }

  return nodeRequire(fullPath);
}

function getTemplatePath(manifest) {
  return (
    manifest?.options?.template_path ||
    manifest?.options?.templatePath ||
    manifest?.template_path ||
    manifest?.templatePath ||
    ""
  );
}

function getItemPath(item) {
  if (typeof item === "string") return item;

  return (
    item?.path ||
    item?.vault_path ||
    item?.vaultPath ||
    item?.file_path ||
    item?.filePath ||
    ""
  );
}

function normalizeManifestPaths(items) {
  const seen = new Set();
  const paths = [];

  for (const item of items || []) {
    const path = String(getItemPath(item) || "").trim();
    if (!path || seen.has(path)) continue;

    seen.add(path);
    paths.push(path);
  }

  return paths;
}

function validateFreshManifest(manifest, maxAgeMs) {
  const timestamp = Number(manifest?.created_at_ms);

  if (!Number.isFinite(timestamp)) {
    return {
      ok: false,
      message: "Apply Template manifest has no valid created_at_ms timestamp."
    };
  }

  const ageMs = Date.now() - timestamp;

  if (ageMs < -5000) {
    return {
      ok: false,
      message: "Apply Template manifest timestamp is in the future. Check the system clock."
    };
  }

  if (ageMs > maxAgeMs) {
    return {
      ok: false,
      message: `Apply Template manifest is stale. Re-check the query selection and run the macro again.`
    };
  }

  return { ok: true, ageMs };
}

module.exports = async function applyTemplateMacro(params = {}) {
  const app = params.app || globalThis.app;

  if (!app) {
    throw new Error("Obsidian app object unavailable.");
  }

  const {
    readManifest,
    getManifestPath,
    getVaultKey
  } = requireFromVault(
    app,
    "_control/scripts/selections/operation-manifest.js"
  );

  const {
    loadTemplateFrontmatter,
    applyTemplateToFile
  } = requireFromVault(
    app,
    "_control/scripts/templates/apply-template-tools.js"
  );

  const operation = "apply-template";
  const maxAgeMs = 10_000;
  const manifestPath = getManifestPath(app, operation);
  const manifest = readManifest(app, operation);

  if (!manifest) {
    notify("No Apply Template manifest found. Save a selection from the Apply Template query first.");
    console.warn("Missing Apply Template manifest:", manifestPath);
    return;
  }

  if (manifest.operation !== operation) {
    notify(`Wrong manifest operation: ${manifest.operation || "unknown"}`);
    console.warn("Wrong Apply Template manifest:", manifest);
    return;
  }

  const expectedVaultKey = getVaultKey(app);
  const manifestVaultKey = manifest?.vault?.key || "";

  if (manifestVaultKey && manifestVaultKey !== expectedVaultKey) {
    notify("Apply Template manifest belongs to a different vault.");
    console.warn("Vault mismatch:", { expectedVaultKey, manifestVaultKey, manifest });
    return;
  }

  const freshness = validateFreshManifest(manifest, maxAgeMs);
  if (!freshness.ok) {
    notify(freshness.message);
    console.warn("Stale Apply Template manifest:", manifest);
    return;
  }

  const templatePath = String(getTemplatePath(manifest) || "").trim();
  if (!templatePath) {
    notify("Apply Template manifest has no template path.");
    console.warn("Manifest missing template path:", manifest);
    return;
  }

  const targetPaths = normalizeManifestPaths(manifest.items);
  if (targetPaths.length === 0) {
    notify("Apply Template manifest has no selected files.");
    console.warn("Manifest has no target paths:", manifest);
    return;
  }

  const { templateFm, create } = await loadTemplateFrontmatter({
    app,
    templatePath
  });

  const results = [];
  const failures = [];

  for (const targetPath of targetPaths) {
    try {
      const result = await applyTemplateToFile({
        app,
        targetPath,
        templateFm,
        create
      });

      results.push(result);
    } catch (error) {
      failures.push({
        path: targetPath,
        error: error?.message || String(error)
      });

      console.error(`apply-template failed for ${targetPath}`, error);
    }
  }

  if (failures.length > 0) {
    notify(
      `Apply Template updated ${results.length} file(s); ${failures.length} failed. See console.`,
      9000
    );

    console.warn("Apply Template failures:", failures);
    return;
  }

  // Deliberately no success Notice. The query view should update as metadata changes.
  console.log("Apply Template complete:", {
    manifestPath,
    templatePath,
    count: results.length,
    results
  });
};