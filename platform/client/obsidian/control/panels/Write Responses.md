# Write Responses

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const path = nodeRequire("node:path");
const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const load = (relative) => nodeRequire(path.join(base, "_control", ...relative.split("/")));
const { renderWriteResponses } = load("scripts/ui/write-responses.js");
await renderWriteResponses({ app, container });
````
