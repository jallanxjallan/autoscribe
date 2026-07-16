const path = require('path');
const { spawnSync } = require('child_process');
const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const { currentSelectionSummary } = require('../lib/selection-loader.js');
const { currentSelectionPath, readCurrentSelection } = require('../selections/current-selection.js');
const { loadControlSnapshot, snapshotList } = require('../lib/control-loader.js');
const { listPlanRecords } = require('../plans/plan-store.js');

const PYTHON_EXECUTABLE = '/home/jeremy/Python3.13Env/bin/python';
const DISPATCH_HELPER = path.join(__dirname, 'dispatch_run.py');

function helperRequest(root, request) {
  const result = spawnSync(PYTHON_EXECUTABLE, [DISPATCH_HELPER], {
    input: JSON.stringify({ ...request, vault_root: root }),
    encoding: 'utf8',
    cwd: root,
    maxBuffer: 16 * 1024 * 1024,
    timeout: 120000,
  });
  let response = null;
  try {
    response = JSON.parse(result.stdout || '{}');
  } catch {
    const detail = (result.stderr || result.stdout || `exit status ${result.status}`).trim();
    throw new Error(`Dispatch helper returned invalid JSON: ${detail || '(empty output)'}`);
  }
  if (result.error) throw new Error(`Dispatch helper could not start: ${result.error.message}`);
  if (result.status !== 0 || response?.ok === false) {
    const detail = response?.error || result.stderr || result.stdout || `exit status ${result.status}`;
    throw new Error(String(detail).trim());
  }
  return response;
}

function uploadedPlans(app) {
  const snapshotResult = loadControlSnapshot();
  if (snapshotResult.error) {
    const detail = snapshotResult.stderr ? `; ${snapshotResult.stderr}` : '';
    throw new Error(`Could not load AutoScribe control snapshot: ${snapshotResult.error}${detail}`);
  }

  const localBySlug = new Map(
    listPlanRecords(app).map((record) => [record.record_identity || record.slug, record])
  );

  return snapshotList(snapshotResult.data, 'plans')
    .map((record) => {
      const ttl = Number(record.ttl);
      return {
        ...record,
        ttl: Number.isFinite(ttl) ? ttl : -2,
        local_record: localBySlug.get(record.slug) || null,
        label: localBySlug.get(record.slug)?.label || record.slug,
      };
    })
    .filter((record) => record.ttl !== -2)
    .sort((a, b) => {
      if (a.ttl !== b.ttl) return b.ttl - a.ttl;
      return String(a.label || a.slug).localeCompare(String(b.label || b.slug));
    });
}

function planStepEntries(plan) {
  const steps = plan?.steps;
  if (Array.isArray(steps)) {
    return steps.map((step, index) => [index + 1, step]).filter(([, step]) => step);
  }
  if (!steps || typeof steps !== 'object') return [];
  return Object.entries(steps)
    .map(([key, step]) => [Number(key), step])
    .filter(([number, step]) => Number.isInteger(number) && number > 0 && step)
    .sort(([a], [b]) => a - b);
}

function planStepCount(plan) {
  const explicit = Number(plan?.step_count);
  if (Number.isInteger(explicit) && explicit >= 0) return explicit;
  return planStepEntries(plan).length;
}

function planOptionText(planFile) {
  const plan = planFile.local_record || planFile;
  const count = Number.isInteger(planFile.step_count) ? planFile.step_count : planStepCount(plan);
  const ttl = planFile.ttl < 0 ? 'persistent' : `${planFile.ttl}s TTL`;
  const steps = Number.isInteger(count) ? `, ${count} step${count === 1 ? '' : 's'}` : '';
  return `${planFile.label || planFile.slug} — ${planFile.slug} (${ttl}${steps})`;
}

function statusText(selection) {
  if (!selection) return 'No current selection loaded.';
  if (!selection.warnings.length) return `${selection.count} file(s) in the current selection.`;
  return `${selection.count} file(s): ${selection.warnings.join('; ')}`;
}

function stateText(item) {
  const values = [
    item.repo_state,
    item.worktree?.label,
    item.dispatch?.state,
    item.process,
    item.raw?.repo_state,
    item.raw?.worktree?.label,
    item.raw?.dispatch?.state,
    item.raw?.process,
  ].map((value) => String(value || '').trim().toLowerCase());

  if (values.some((value) => value === 'conflicted' || value === 'conflict')) return 'conflicted';
  if (values.some((value) => ['inflight', 'in-flight', 'queued', 'running', 'dispatched'].includes(value))) return 'inflight';
  if (values.some((value) => ['processed', 'written', 'complete', 'completed'].includes(value))) return 'processed';
  if (values.some((value) => ['dirty', 'editing', 'modified', 'untracked', 'staged'].includes(value))) return 'dirty';
  return 'clean';
}


function renderPromptTable(container, items) {
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'Filename', 'Slug', 'State'].map((h) => el('th', { text: h }))));
  for (const item of items) {
    table.appendChild(el('tr', {}, [
      el('td', { text: item.index }),
      el('td', { text: item.path ? path.basename(item.path) : item.label }),
      el('td', { text: item.slug || '—' }),
      el('td', { text: stateText(item) }),
    ]));
  }
  container.appendChild(table);
}

function refLabel(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.label || value.key || value.slug || '';
}

function stepTargetText(step) {
  const script = refLabel(step.script);
  const rag = refLabel(step.rag_profile);
  const engine = refLabel(step.engine);
  if (script) return `script: ${script}`;
  if (rag) return `rag: ${rag}`;
  if (engine) return `engine: ${engine}`;
  return '—';
}

function stepInstructionText(step) {
  if (Array.isArray(step.instructions)) return step.instructions.map(refLabel).filter(Boolean).join(', ');
  if (Array.isArray(step.instruction_slugs)) return step.instruction_slugs.filter(Boolean).join(', ');
  return '';
}

function renderPlanTable(container, plan) {
  const entries = planStepEntries(plan);
  if (!entries.length) {
    container.appendChild(el('p', { text: 'Selected plan has no steps.' }));
    return;
  }
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'Step', 'Target', 'Instructions'].map((h) => el('th', { text: h }))));
  entries.forEach(([number, step]) => {
    table.appendChild(el('tr', {}, [
      el('td', { text: step.index || number }),
      el('td', { text: step.label || `Step ${number}` }),
      el('td', { text: stepTargetText(step) }),
      el('td', { text: stepInstructionText(step) || '—' }),
    ]));
  });
  container.appendChild(table);
}

function readableMessages(response) {
  if (Array.isArray(response?.messages)) return response.messages.map(String).join('\n');
  if (Array.isArray(response?.output)) return response.output.map(String).join('\n');
  for (const key of ['message', 'stdout', 'output', 'detail']) {
    if (typeof response?.[key] === 'string' && response[key].trim()) return response[key].trim();
  }
  return JSON.stringify(response, null, 2);
}

async function renderCreateRun({ app, container }) {
  clear(container);
  const root = vaultRoot(app);
  const plans = uploadedPlans(app);
  let loadedSelection = null;

  container.appendChild(el('h2', { text: 'Dispatch Run' }));
  container.appendChild(el('p', { text: 'Automatically loads the live current selection. Dispatch resolves and commits the live selection, streams absolute paths and plan metadata through xargs/Pandoc, then pipes Pandoc NDJSON to `asc enqueue`.' }));

  const planSelect = el('select');
  planSelect.style.width = '100%';
  if (!plans.length) {
    planSelect.appendChild(el('option', { text: 'No uploaded plans found.' }));
    planSelect.disabled = true;
  } else {
    for (const plan of plans) planSelect.appendChild(el('option', { value: plan.slug, text: planOptionText(plan) }));
  }

  const summary = el('p', { text: 'No current selection loaded.' });
  const promptBox = el('div');
  const planBox = el('div');
  const output = el('pre', { text: '' });
  output.style.whiteSpace = 'pre-wrap';

  function selectedPlan() {
    return plans.find((p) => p.slug === planSelect.value) || null;
  }

  function refreshPreview() {
    promptBox.innerHTML = '';
    planBox.innerHTML = '';
    const current = readCurrentSelection(app);
    loadedSelection = current ? currentSelectionSummary(app, current, currentSelectionPath(app)) : null;
    summary.textContent = statusText(loadedSelection);

    promptBox.appendChild(el('h3', { text: 'Current selection' }));
    if (loadedSelection) renderPromptTable(promptBox, loadedSelection.items);
    else promptBox.appendChild(el('p', { text: 'Save a current selection from a query, then refresh this panel.' }));

    const plan = selectedPlan();
    planBox.appendChild(el('h3', { text: 'Plan steps' }));
    if (plan) {
      planBox.appendChild(el('p', { text: `${plan.label || plan.slug} — ${plan.slug}` }));
      const planRecord = plan.local_record || null;
      if (planRecord) renderPlanTable(planBox, planRecord);
      else planBox.appendChild(el('p', { text: 'Uploaded plan details are not present in the local plan cache.' }));
    } else {
      planBox.appendChild(el('p', { text: 'No plan selected.' }));
    }
  }

  planSelect.addEventListener('change', refreshPreview);

  const refreshBtn = button('Refresh', async () => {
    try {
      await renderCreateRun({ app, container });
    } catch (error) {
      new Notice(`Dispatch Run refresh failed: ${error.message}`, 10000);
      console.error(error);
    }
  });

  const dispatchBtn = button('Dispatch Run', () => {
    try {
      refreshPreview();
      const plan = selectedPlan();
      if (!loadedSelection?.items?.length) throw new Error(`The current selection at ${currentSelectionPath(app)} contains no usable file records.`);
      if (!plan?.slug) throw new Error('Select an uploaded plan.');
      const items = loadedSelection.items.map((item) => ({ path: item.path, slug: item.slug }));
      if (items.some((item) => !item.path)) throw new Error('Every selected item must have a filepath.');
      if (items.some((item) => !item.slug)) throw new Error('Every selected item must have a slug.');

      dispatchBtn.disabled = true;
      output.textContent = 'Dispatching…';
      const response = helperRequest(root, {
        operation: 'dispatch',
        items,
        plan_slug: plan.slug,
      });
      output.textContent = readableMessages(response);
      new Notice('Dispatch complete.');
      refreshPreview();
    } catch (error) {
      output.textContent = error.message;
      new Notice(`Dispatch failed: ${error.message}`, 10000);
      console.error(error);
    } finally {
      dispatchBtn.disabled = false;
    }
  });

  const controls = el('div');
  controls.style.display = 'grid';
  controls.style.gridTemplateColumns = '1fr';
  controls.style.gap = '0.5rem';
  controls.append(el('label', {}, ['Uploaded plan', planSelect]), summary);

  const buttonRow = el('div');
  buttonRow.style.display = 'flex';
  buttonRow.style.gap = '0.5rem';
  buttonRow.append(refreshBtn, dispatchBtn);
  controls.append(buttonRow);

  container.append(controls, promptBox, planBox, output);
  refreshPreview();
}

module.exports = { renderCreateRun };
