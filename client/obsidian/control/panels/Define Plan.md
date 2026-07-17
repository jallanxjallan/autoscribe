
```dataviewjs
const helperPath = `${app.vault.adapter.basePath}/_control/scripts/plans/render-create-plan.js`;
const { renderCreatePlan } = require(helperPath);
await renderCreatePlan({ app, container: this.container });
```
