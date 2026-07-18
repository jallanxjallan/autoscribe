const path = require('path');
const { spawnSync } = require('child_process');
const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const { currentSelectionSummary } = require('../lib/selection-loader.js');
const { currentSelectionPath, readCurrentSelection } = require('../selections/current-selection.js');
const { loadControlSnapshot, snapshotList } = require('../lib/control-loader.js');

const PYTHON_EXECUTABLE = '/home/jeremy/Python3.13Env/bin/python';
const DISPATCH_HELPER = path.join(__dirname, 'dispatch_run.py');
const LIVE_SELECTION_INTERVAL_MS = 1000;

function helperRequest(root, request) {
  const result = spawnSync(PYTHON_EXECUTABLE, [DISPATCH_HELPER], {
    input: JSON.stringify({ ...request, vault_root: root }),
    encoding: 'utf8',
    cwd: root,
    maxBuffer: 16 * 1024 * 1024,
    timeout: 120000,
  });
  let response;
  try {
    response = JSON.parse(result.stdout || '{}');
  } catch {
    const detail = (result.stderr || result.stdout || `exit status ${result.status}`).trim();
    throw new Error(`Dispatch helper returned invalid JSON: ${detail || '(empty output)'}`);
  }
  if (result.error) throw new Error(`Dispatch helper could not start: ${result.error.message}`);
  if (result.status !== 0 || response?.ok === false) {
    throw new Error(String(response?.error || result.stderr || result.stdout || `exit status ${result.status}`).trim());
  }
  return response;
}

function loadPlans() {
  const snapshot = loadControlSnapshot();
  if (snapshot.error) {
    const detail = snapshot.stderr ? `; ${snapshot.stderr}` : '';
    throw new Error(`Could not load AutoScribe control snapshot: ${snapshot.error}${detail}`);
  }
  return snapshotList(snapshot.data, 'plans')
    .map((record) => ({
      ...record,
      ttl: Number.isFinite(Number(record.ttl)) ? Number(record.ttl) : -2,
      label: record.label || record.slug,
    }))
    .filter((record) => record.ttl !== -2)
    .sort((a, b) => b.ttl - a.ttl || String(a.label).localeCompare(String(b.label)));
}

function planOptionText(plan) {
  const ttl = plan.ttl < 0 ? 'persistent' : `${plan.ttl}s TTL`;
  return `${plan.label} — ${plan.slug} (${ttl})`;
}

function selectionSignature(selection) {
  if (!selection?.items) return '';
  return selection.items.map((item) => `${item.path || ''}\0${item.slug || ''}`).join('\1');
}

function renderFileTable(container, items) {
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'Filename', 'Slug'].map((heading) => el('th', { text: heading }))));
  for (const item of items) {
    table.appendChild(el('tr', {}, [
      el('td', { text: item.index }),
      el('td', { text: item.path ? path.basename(item.path) : item.label }),
      el('td', { text: item.slug || '—' }),
    ]));
  }
  container.appendChild(table);
}

function readableMessage(response) {
  const result = response?.result || {};
  const lines = [];
  if (response?.message) lines.push(String(response.message));
  for (const failure of result.failures || []) {
    lines.push(`FAILED  ${failure.slug || failure.path}: ${failure.error}`);
  }
  if (result.pipeline_output) lines.push(String(result.pipeline_output));
  return lines.join('\n') || JSON.stringify(response, null, 2);
}

async function renderCreateRun({ app, container }) {
  if (container.__dispatchSelectionTimer) clearInterval(container.__dispatchSelectionTimer);
  clear(container);

  const root = vaultRoot(app);
  let plans = loadPlans();
  let loadedSelection = null;
  let lastSelectionSignature = null;

  container.appendChild(el('h2', { text: 'Dispatch Run' }));

  const selectionControls = el('div');
  selectionControls.style.display = 'flex';
  selectionControls.style.gap = '0.5rem';
  selectionControls.style.alignItems = 'center';

  const loadSelectionBtn = button('Load saved selection', () => loadSelection(true));
  const selectionSummary = el('span', { text: 'No saved selection loaded.' });
  selectionControls.append(loadSelectionBtn, selectionSummary);
  container.appendChild(selectionControls);

  const planRow = el('div');
  planRow.style.display = 'flex';
  planRow.style.gap = '0.5rem';
  planRow.style.alignItems = 'center';

  const planSelect = el('select');
  planSelect.style.flex = '1';

  function fillPlans(preferredSlug = '') {
    planSelect.innerHTML = '';
    if (!plans.length) {
      planSelect.appendChild(el('option', { text: 'No uploaded plans found.' }));
      planSelect.disabled = true;
      return;
    }
    planSelect.disabled = false;
    for (const plan of plans) {
      planSelect.appendChild(el('option', { value: plan.slug, text: planOptionText(plan) }));
    }
    if (preferredSlug && plans.some((plan) => plan.slug === preferredSlug)) {
      planSelect.value = preferredSlug;
    }
  }

  const refreshPlansBtn = button('Refresh', () => {
    const selected = planSelect.value;
    plans = loadPlans();
    fillPlans(selected);
  });

  fillPlans();
  planRow.append(el('label', {}, ['Uploaded plan ', planSelect]), refreshPlansBtn);
  container.appendChild(planRow);

  const filesBox = el('div');
  const output = el('pre', { text: '' });
  output.style.whiteSpace = 'pre-wrap';

  function loadSelection(forceRender = false) {
    const current = readCurrentSelection(app);
    const next = current
      ? currentSelectionSummary(app, current, currentSelectionPath(app))
      : null;
    const signature = selectionSignature(next);
    if (!forceRender && signature === lastSelectionSignature) return;

    loadedSelection = next;
    lastSelectionSignature = signature;
    filesBox.innerHTML = '';

    if (!loadedSelection?.items?.length) {
      selectionSummary.textContent = 'No usable files in the saved selection.';
      filesBox.appendChild(el('p', { text: 'Save a selection from a query.' }));
      return;
    }

    selectionSummary.textContent = `${loadedSelection.count} file(s) loaded.`;
    renderFileTable(filesBox, loadedSelection.items);
  }

  const dispatchBtn = button('Dispatch Run', () => {
    try {
      loadSelection(true);
      const planSlug = planSelect.value;
      if (!loadedSelection?.items?.length) throw new Error('The saved selection contains no usable files.');
      if (!planSlug) throw new Error('Select an uploaded plan.');

      dispatchBtn.disabled = true;
      output.textContent = 'Dispatching…';
      const response = helperRequest(root, {
        operation: 'dispatch',
        plan_slug: planSlug,
        items: loadedSelection.items.map((item) => ({ path: item.path, slug: item.slug })),
      });
      output.textContent = readableMessage(response);
      new Notice('Dispatch complete.');
      loadSelection(true);
    } catch (error) {
      output.textContent = error.message;
      new Notice(`Dispatch failed: ${error.message}`, 10000);
      console.error(error);
    } finally {
      dispatchBtn.disabled = false;
    }
  });

  container.append(filesBox, dispatchBtn, output);
  loadSelection(true);
  container.__dispatchSelectionTimer = setInterval(() => loadSelection(false), LIVE_SELECTION_INTERVAL_MS);
}

module.exports = { renderCreateRun };
