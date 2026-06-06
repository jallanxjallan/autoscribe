'use strict';

const { makeSlug } = require('../lib/slug');
const { saveSelection } = require('./selection-store.js');

function valueOf(page, key) {
  const value = page[key];
  if (value === undefined || value === null) return '';
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

function promptFileRecord(page) {
  return {
    path: page.file.path,
    name: page.file.name,
    slug: valueOf(page, 'slug'),
    title: valueOf(page, 'title') || page.file.name,
    status: valueOf(page, 'status'),
    stage: valueOf(page, 'stage'),
    process: valueOf(page, 'process'),
    repo_state: valueOf(page, 'repo_state') || valueOf(page, 'git')
  };
}

function checkbox(checked = false) {
  const el = document.createElement('input');
  el.type = 'checkbox';
  el.checked = checked;
  return el;
}

function button(label, onClick) {
  const b = document.createElement('button');
  b.textContent = label;
  b.onclick = onClick;
  return b;
}

function input(placeholder) {
  const i = document.createElement('input');
  i.placeholder = placeholder;
  i.style.width = '100%';
  i.style.margin = '0.25rem 0';
  return i;
}

async function renderContentSelection({ app, dv, container, pages, defaultLabel = 'Current selection' }) {
  const root = document.createElement('div');
  container.appendChild(root);

  const title = document.createElement('h2');
  title.textContent = 'Select Prompts';
  root.appendChild(title);

  const labelInput = input('Selection label');
  labelInput.value = defaultLabel;
  root.appendChild(labelInput);

  const rows = pages.map((page) => ({ page, selected: checkbox(false) }));

  const tbl = document.createElement('table');
  tbl.style.width = '100%';
  const head = document.createElement('tr');
  ['Use', 'Title', 'Slug', 'Status', 'Stage', 'Repo'].forEach((h) => {
    const th = document.createElement('th');
    th.textContent = h;
    head.appendChild(th);
  });
  tbl.appendChild(head);

  for (const row of rows) {
    const rec = promptFileRecord(row.page);
    const tr = document.createElement('tr');
    const tdUse = document.createElement('td');
    tdUse.appendChild(row.selected);
    tr.appendChild(tdUse);
    for (const key of ['title', 'slug', 'status', 'stage', 'repo_state']) {
      const td = document.createElement('td');
      td.textContent = rec[key] || '';
      tr.appendChild(td);
    }
    tbl.appendChild(tr);
  }
  root.appendChild(tbl);

  root.appendChild(button('Save Selection Manifest', async () => {
    const files = rows.filter((r) => r.selected.checked).map((r) => promptFileRecord(r.page));
    if (!files.length) throw new Error('No files selected.');
    const label = labelInput.value.trim() || 'Current selection';
    const slug = makeSlug('sel', label);
    await saveSelection(app, slug, {
      type: 'selection',
      slug,
      selection_slug: slug,
      label,
      created: new Date().toISOString(),
      files
    });
    new Notice(`Saved selection ${slug} (${files.length} files)`);
  }));
}

module.exports = { renderContentSelection };
