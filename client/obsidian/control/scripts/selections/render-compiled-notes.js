const path = require('path');
const { el, clear } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const { listSelections, selectionSummary } = require('../lib/selection-loader.js');

function activeVaultPrefix(app) {
  const root = vaultRoot(app);
  return path.basename(root).toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function newestActiveSelection(app, selections) {
  const prefix = activeVaultPrefix(app);
  const local = selections.filter((s) => String(s.vaultKey || '').startsWith(prefix));
  return (local.length ? local : selections).slice().sort((a, b) => b.mtime_ms - a.mtime_ms)[0] || null;
}

function itemPath(item) {
  return item.path || item.file || item.file_path || item.vault_path || '';
}

function itemTitle(item, file) {
  return item.title || item.label || item.slug || file?.basename || itemPath(item);
}

function obsidianLink(pathValue, title) {
  return `[[${pathValue}|${title}]]`;
}

function transclusion(pathValue) {
  return `![[${pathValue}]]`;
}

function renderMissing(container, message) {
  container.appendChild(el('p', { text: message }));
}

async function renderCompiledNotes({ app, dv, container }) {
  clear(container);

  const root = vaultRoot(app);
  const selections = listSelections(app);
  const active = newestActiveSelection(app, selections);

  container.appendChild(el('h2', { text: 'Compiled Notes' }));
  container.appendChild(el('p', {}, [
    'Helper path: ',
    el('code', { text: `${root}/_control/scripts/selections/render-compiled-notes.js` }),
  ]));

  if (!active) {
    renderMissing(container, 'No saved selection manifests found.');
    return;
  }

  const selection = selectionSummary(app, active.file);
  const items = Array.isArray(selection.items) ? selection.items : [];

  container.appendChild(el('p', {}, [
    'Saved selection: ',
    el('code', { text: active.name || path.basename(active.file) }),
    ` — ${items.length} item${items.length === 1 ? '' : 's'}`,
  ]));

  if (!items.length) {
    renderMissing(container, 'Saved selection has no items.');
    return;
  }

  for (const item of items) {
    const vaultPath = itemPath(item);

    if (!vaultPath) {
      container.appendChild(el('h3', { text: 'Missing path' }));
      container.appendChild(el('pre', { text: JSON.stringify(item, null, 2) }));
      continue;
    }

    const file = app.vault.getAbstractFileByPath(vaultPath);

    if (!file) {
      container.appendChild(el('h3', { text: vaultPath }));
      container.appendChild(el('p', { text: `File not found: ${vaultPath}` }));
      continue;
    }

    const title = itemTitle(item, file);

    dv.header(2, obsidianLink(vaultPath, title));
    dv.paragraph(transclusion(vaultPath));
  }
}

module.exports = { renderCompiledNotes };