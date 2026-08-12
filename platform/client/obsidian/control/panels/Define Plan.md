# Define Plan

```dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const implementation = pathMod.join(vaultRoot, "_control", "scripts", "ui", "define-plan.js");

try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}
const { renderCreatePlan } = nodeRequire(implementation);
await renderCreatePlan({ app, container: dv.container });
```
