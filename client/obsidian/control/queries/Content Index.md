```dataviewjs
const CONFIG = {
  tocPath: "",
  tempRoot: "",
  debug: false,

  slugPrefixes: ["cnt_", "img_"],

  unicodeReference: [
    { symbol: "❦", code: "U+2766", label: "motif", meaning: "Motif" },
    { symbol: "▣", code: "U+25A3", label: "boxout", meaning: "Boxout" },
    { symbol: "◈", code: "U+25C8", label: "feature", meaning: "Feature" },
    { symbol: "¶", code: "U+00B6", label: "narrative", meaning: "Narrative" },
    { symbol: "▯", code: "U+25AF", label: "single", meaning: "Single page" },
    { symbol: "▭", code: "U+25AD", label: "double", meaning: "Double page" },
  ],

  defaultClass: "—",
  defaultTags: "—",
  defaultLayoutComponent: "—",

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
const runtime = createQueryRuntime({ app, queryTitle: "Content Index query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { makeContentIndexView } = loader.requireControl("scripts/lib/content-index-view.js");

await makeContentIndexView({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,
  queryPath,
  vaultName,
  config: CONFIG,
  renderSelectionQuery,
}).render();
```
