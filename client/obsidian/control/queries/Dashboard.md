# Vault Dashboard

> [!summary] Control surface
> Use this page as the F3 cockpit for the current vault: query links, public content, saved selections, provisional notes, and hygiene checks.

```dataviewjs
const CONFIG = {
  contentPrefixes: ["pss", "img", "scn"],
  provisionalPrefix: "prv",

  queryFolder: "_control/queries",

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

const runtimePath = pathMod.join(
  vaultBasePath,
  ...controlRootForBootstrap.split("/").filter(Boolean),
  "scripts",
  "lib",
  "query-runtime.js"
);

const { createQueryRuntime } = nodeRequire(runtimePath);
const runtime = createQueryRuntime({ app, queryTitle: "Vault Dashboard" });
const { loader } = runtime;

const { renderVaultDashboard } = loader.requireControl(
  "scripts/dashboard-query.js"
);

await renderVaultDashboard({
  app,
  dv,
  runtime,
  config: CONFIG
});
```
