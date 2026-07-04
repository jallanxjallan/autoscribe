```dataviewjs
const CONFIG = {
  tempRoot: "",
  debug: false,

  defaultStatus: "—",
  defaultStage: "—",
  defaultProcess: "—",
  defaultSlugPrefix: "—",

  excludePaths: [
    ".obsidian",
    ".trash",
    ".autoscribe",
  ],
};

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPathForBootstrap = app.workspace.getActiveFile().path;
const markerIndexForBootstrap = queryPathForBootstrap.indexOf("/queries/");

if (markerIndexForBootstrap === -1) {
  throw new Error(`Query is not inside a queries folder: ${queryPathForBootstrap}`);
}

const controlRootForBootstrap = queryPathForBootstrap.slice(0, markerIndexForBootstrap);
const runtimePath = pathMod.join(
  vaultBasePath,
  ...controlRootForBootstrap.split("/").filter(Boolean),
  "scripts",
  "lib",
  "query-runtime.js"
);

const { createQueryRuntime } = nodeRequire(runtimePath);
const runtime = createQueryRuntime({ app, queryTitle: "Content Status query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { makeContentStatusView } = loader.requireControl("scripts/lib/content-status-view.js");

await makeContentStatusView({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,
  queryPath,
  vaultName,
  config: CONFIG,
  renderSelectionQuery,
}).render();
```
