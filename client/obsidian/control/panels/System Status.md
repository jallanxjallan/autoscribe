# System Status

```dataviewjs
const vaultRoot = app.vault.adapter.basePath;
const { renderSystemStatus } = require(`${vaultRoot}/_control/scripts/status/render-system-status.js`);
renderSystemStatus({ app, container: this.container });
```
