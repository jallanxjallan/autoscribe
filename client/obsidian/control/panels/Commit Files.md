# Commit Files

```dataviewjs
const vaultRoot = app.vault.adapter.basePath;
const { renderCommitFiles } = require(`${vaultRoot}/_control/scripts/commits/render-commit-files.js`);
await renderCommitFiles({ app, container: dv.container });
```
