# Vault Dashboard

> [!summary] Control surface
> Use this page as the F3 cockpit for the current vault: query links, public content, saved selections, provisional notes, and hygiene checks.

```dataviewjs
const CONFIG = {
  contentPrefixes: ["pss", "img", "scn"],
  provisionalPrefix: "prv",

  queryFolder: "_control/queries",
  panelFolder: "_control/panels",

  selectionDir: ".autoscribe/selections",

  recentLimit: 20,
  missingSlugLimit: 50
};

const nodeRequire =
  typeof require === "function"
    ? require
    : window.require;

const pathMod = nodeRequire("path");

const vaultBasePath =
  app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;

const activePath = app.workspace.getActiveFile()?.path || "";
const activeSegments = activePath.split("/").filter(Boolean);
const controlIndex = activeSegments.indexOf("_control");

const controlRootForBootstrap =
  controlIndex >= 0
    ? activeSegments.slice(0, controlIndex + 1).join("/")
    : "_control";

const fsMod = nodeRequire("fs");
const queryPath = activePath;
const vaultName = String(
  app.vault.getName?.() || app.vault.name || "vault"
).trim() || "vault";

const vaultControlRootPath = pathMod.join(
  vaultBasePath,
  ...controlRootForBootstrap.split("/").filter(Boolean)
);
const controlRootPath = fsMod.realpathSync(vaultControlRootPath);

const loader = {
  nodeRequire,
  pathMod,
  fsMod,
  vaultBasePath,
  queryPath,
  controlRoot: controlRootForBootstrap,
  vaultControlRootPath,
  controlRootPath,
  controlPath(relativePath) {
    return [controlRootForBootstrap, relativePath]
      .filter(Boolean)
      .join("/");
  },
  nativePath(vaultRelativePath) {
    return pathMod.join(
      vaultBasePath,
      ...String(vaultRelativePath).split("/").filter(Boolean)
    );
  },
  requireControl(relativePath) {
    return nodeRequire(pathMod.join(
      controlRootPath,
      ...String(relativePath).split(/[\\/]+/).filter(Boolean)
    ));
  }
};

async function openQuery(queryLink, sourcePath = queryPath) {
  const queryFile =
    typeof queryLink === "string"
      ? app.metadataCache.getFirstLinkpathDest(queryLink, sourcePath)
      : queryLink;

  if (!queryFile?.path) {
    throw new Error(`Query not found: ${String(queryLink)}`);
  }

  const existingLeaf = app.workspace.getLeavesOfType("markdown").find(
    leaf => leaf.view?.file?.path === queryFile.path
  );

  if (existingLeaf) {
    await app.workspace.revealLeaf(existingLeaf);
    return existingLeaf;
  }

  const leaf = app.workspace.getLeaf("tab");
  await leaf.openFile(queryFile);
  await app.workspace.revealLeaf(leaf);
  return leaf;
}

const runtime = {
  app,
  nodeRequire,
  loader,
  pathMod,
  vaultBasePath,
  vaultName,
  queryPath,
  controlRoot: controlRootForBootstrap,
  controlLoaderPath: null,
  openQuery
};

const { renderVaultDashboard } = loader.requireControl(
  "scripts/dashboard-query.js"
);

await renderVaultDashboard({
  app,
  dv,
  runtime,
  config: CONFIG
});

const dashboardContainer = dv.container;

if (!dashboardContainer.dataset.queryOpenGuard) {
  dashboardContainer.dataset.queryOpenGuard = "true";

  dashboardContainer.addEventListener("click", async event => {
    const link = event.target.closest("a.internal-link");
    if (!link || !dashboardContainer.contains(link)) return;

    const linkTarget = link.dataset.href || link.getAttribute("href") || "";
    const queryFile = app.metadataCache.getFirstLinkpathDest(
      linkTarget,
      queryPath
    );

    const queryFolderPrefix = `${CONFIG.queryFolder.replace(/\/+$/, "")}/`;
    if (!queryFile?.path?.startsWith(queryFolderPrefix)) return;

    event.preventDefault();
    event.stopPropagation();
    await openQuery(queryFile);
  });
}
```
