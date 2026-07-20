# Write Responses

```dataviewjs
const vaultRoot = app.vault.adapter.basePath;
const { renderWriteResponses } = require(`${vaultRoot}/_control/scripts/responses/render-write-responses.js`);
await renderWriteResponses({ app, container: dv.container });
```
