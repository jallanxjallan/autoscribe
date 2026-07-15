> [!NOTE] Dispatch Run
> Select a user commit and an uploaded plan, then dispatch the committed files.

```dataviewjs
const helperPath = `${app.vault.adapter.basePath}/_control/scripts/runs/render-create-run.js`;
const { renderCreateRun } = require(helperPath);
await renderCreateRun({ app, dv, container: this.container });
```
