# Plan History

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));
const { renderPlanHistory } = loadControl("scripts/ui/plan-history.js");

renderPlanHistory({ app, container: dv.container });
````
