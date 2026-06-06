```dataviewjs
const CONFIG = {
  slugPrefixes: [],
  excludePaths: [],
  tempRoot: "",
  debug: false
};

const nodeRequire =
  typeof require === "function"
    ? require
    : window.require;

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
const { loader } = runtime;

const { renderStatusQuery } = loader.requireControl(
  "scripts/status-query-runner.js"
);

await renderStatusQuery({
  app,
  dv,
  runtime,
  config: CONFIG,

  scope: "public",
  title: "Content Status",
  namespace: "content-status",
  bridgeName: "__contentStatusSelection",
  operation: "content-status",
  queryName: "Content Status",

  emptyMessage: "No public Markdown files with frontmatter `slug` were found.",
  noMatchesMessage: "No matching public slugged files."
});
```