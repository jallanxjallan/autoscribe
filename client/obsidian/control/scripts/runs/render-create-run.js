const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot, workflowDir, safeReadJson, statInfo } = require('../lib/vault-state.js');
const { currentSelectionSummary } = require('../lib/selection-loader.js');
const { currentSelectionPath, readCurrentSelection } = require('../selections/current-selection.js');

const OBS_EXECUTABLE = '/home/jeremy/Python3.13Env/bin/obs';

function listPlans(app) {
  const dir = workflowDir(app, 'plans');
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter((name) => name.endsWith('.json'))
    .map((name) => {
      const file = path.join(dir, name);
      const record = safeReadJson(file, null);
      const stat = statInfo(file);
      return { file, name, record, mtime_ms: stat.mtime_ms || 0, mtime: stat.mtime };
    })
    .filter((item) => item.record?.slug)
    .sort((a, b) => String(a.record.label || a.record.slug).localeCompare(String(b.record.label || b.record.slug)));
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
  const plan = planFile.record;
  const count = planStepCount(plan);
  return `${plan.label || plan.slug} — ${plan.slug} (${count} step${count === 1 ? '' : 's'})`;
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

function lastUserCommitText(item) {
  const commit = item.user_commit || item.raw?.user_commit || null;
  if (commit) {
    const hash = String(commit.hash || commit.commit || '').slice(0, 8);
    const subject = String(commit.subject || '').trim();
    return [hash, subject].filter(Boolean).join(' · ') || '—';
  }
  const hash = String(item.short_commit || item.git_commit || '').slice(0, 8);
  const subject = String(item.git_subject || '').trim();
  return [hash, subject].filter(Boolean).join(' · ') || '—';
}

function renderPromptTable(container, items) {
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'Filename', 'Slug', 'Last user commit', 'State'].map((h) => el('th', { text: h }))));
  for (const item of items) {
    table.appendChild(el('tr', {}, [
      el('td', { text: item.index }),
      el('td', { text: item.path ? path.basename(item.path) : item.label }),
      el('td', { text: item.slug || '—' }),
      el('td', { text: lastUserCommitText(item) }),
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

function ipc(root, request) {
  const result = spawnSync(OBS_EXECUTABLE, ['--vault', root, 'ipc'], {
    input: JSON.stringify(request),
    encoding: 'utf8',
    cwd: root,
    maxBuffer: 16 * 1024 * 1024,
    timeout: 120000,
  });
  if (result.error) throw new Error(`obs IPC could not start: ${result.error.message}`);
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || `exit status ${result.status}`).trim();
    throw new Error(detail || `obs IPC exited with status ${result.status}`);
  }
  let response;
  try {
    response = JSON.parse(result.stdout);
  } catch {
    throw new Error(`obs IPC returned invalid JSON:\n${result.stdout || '(empty output)'}`);
  }
  if (response?.ok === false) throw new Error(response.error || response.message || 'Dispatch failed');
  return response;
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
  const plans = listPlans(app);
  let loadedSelection = null;

  container.appendChild(el('h2', { text: 'Dispatch Run' }));
  container.appendChild(el('p', { text: 'Uses the live current selection for this vault session.' }));

  const planSelect = el('select');
  planSelect.style.width = '100%';
  if (!plans.length) {
    planSelect.appendChild(el('option', { text: 'No uploaded plans found.' }));
    planSelect.disabled = true;
  } else {
    for (const plan of plans) planSelect.appendChild(el('option', { value: plan.file, text: planOptionText(plan) }));
  }

  const summary = el('p', { text: 'No current selection loaded.' });
  const promptBox = el('div');
  const planBox = el('div');
  const output = el('pre', { text: '' });
  output.style.whiteSpace = 'pre-wrap';

  function selectedPlan() {
    return plans.find((p) => p.file === planSelect.value)?.record || null;
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
      renderPlanTable(planBox, plan);
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
      if (!loadedSelection?.items?.length) throw new Error('The current selection is empty.');
      if (!plan?.slug) throw new Error('Select an uploaded plan.');
      const paths = loadedSelection.items.map((item) => item.path).filter(Boolean);
      if (paths.length !== loadedSelection.items.length) throw new Error('Every selected item must have a filepath.');

      dispatchBtn.disabled = true;
      output.textContent = 'Dispatching…';
      const response = ipc(root, {
        operation: 'dispatch_run.enqueue',
        paths,
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
