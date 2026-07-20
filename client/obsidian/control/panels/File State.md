# File State

```dataviewjs
const vaultRoot = app.vault.adapter.basePath;
const { renderFileState } = require(`${vaultRoot}/_control/scripts/files/render-file-state.js`);
await renderFileState({ app, container: dv.container });
```
