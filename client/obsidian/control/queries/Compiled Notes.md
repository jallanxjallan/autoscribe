```dataviewjs
const helperPath = `${app.vault.adapter.basePath}/_control/scripts/selections/render-compiled-notes.js`;
const { renderCompiledNotes } = require(helperPath);
await renderCompiledNotes({ app, dv, container: this.container });
```