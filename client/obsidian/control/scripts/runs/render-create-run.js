const fs = require('fs');
const path = require('path');
const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot, workflowDir, safeReadJson, statInfo } = require('../lib/vault-state.js');
const { listSelections, selectionSummary } = require('../lib/selection-loader.js');
const { buildRunManifest, saveRunManifest } = require('./run-manifest.js');

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

function activeVaultPrefix(app) {
  const root = vaultRoot(app);
  return path.basename(root).toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function newestActiveSelection(app, selections) {
  const prefix = activeVaultPrefix(app);
  const local = selections.filter((s) => String(s.vaultKey || '').startsWith(prefix));
  return (local.length ? local : selections).slice().sort((a, b) => b.mtime_ms - a.mtime_ms)[0] || null;
}

function selectionOptionText(sel, tag = '') {
  const warn = sel.warnings?.length ? ` — ${sel.warnings.join('; ')}` : '';
  return `${tag}${sel.name} (${sel.count}) — ${sel.vaultKey}${warn}`;
}

function planOptionText(planFile) {
  const plan = planFile.record;
  const count = Array.isArray(plan.steps) ? plan.steps.length : 0;
  return `${plan.label || plan.slug} — ${plan.slug} (${count} step${count === 1 ? '' : 's'})`;
}

function statusText(selection) {
  if (!selection) return 'No selection loaded.';
  if (!selection.warnings.length) return `${selection.count} prompt(s), all clean/current by manifest preflight.`;
  return `${selection.count} prompt(s): ${selection.warnings.join('; ')}`;
}

function renderPromptTable(container, items) {
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'Filename', 'Slug', 'Status', 'Stage', 'Repo'].map((h) => el('th', { text: h }))));
  for (const item of items) {
    table.appendChild(el('tr', {}, [
      el('td', { text: item.index }),
      el('td', { text: item.path ? path.basename(item.path) : item.label }),
      el('td', { text: item.slug || '—' }),
      el('td', { text: item.status || '—' }),
      el('td', { text: item.stage || '—' }),
      el('td', { text: item.repo_state || '—' }),
    ]));
  }
  container.appendChild(table);
}

function stepTargetText(step) {
  const script = step.script?.label || step.script?.key || step.script?.slug;
  const rag = step.rag_profile?.label || step.rag_profile?.key || step.rag_profile?.slug;
  const engine = step.engine?.label || step.engine?.key || step.engine?.slug;
  if (script) return `script: ${script}`;
  if (rag) return `rag: ${rag}`;
  if (engine) return `engine: ${engine}`;
  return '—';
}

function renderPlanTable(container, plan) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  if (!steps.length) {
    container.appendChild(el('p', { text: 'Selected plan has no steps.' }));
    return;
  }
  const table = el('table');
  table.style.width = '100%';
  table.appendChild(el('tr', {}, ['#', 'Step', 'Target', 'Instructions'].map((h) => el('th', { text: h }))));
  steps.forEach((step, idx) => {
    table.appendChild(el('tr', {}, [
      el('td', { text: step.index || idx + 1 }),
      el('td', { text: step.label || `Step ${idx + 1}` }),
      el('td', { text: stepTargetText(step) }),
      el('td', { text: (step.instructions || []).map((ins) => ins.label || ins.slug).join(', ') || '—' }),
    ]));
  });
  container.appendChild(table);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    new Notice('Copied.');
  } catch {
    new Notice('Clipboard copy failed.');
  }
}

async function renderCreateRun({ app, container }) {
  clear(container);
  const root = vaultRoot(app);
  const selections = listSelections(app);
  const plans = listPlans(app);
  let loadedSelection = null;

  container.appendChild(el('h2', { text: 'Run' }));
  container.appendChild(el('p', { text: 'A run is a local upload queue: selected prompts plus a saved plan. The durable server-side organizing unit remains the call.' }));
  container.appendChild(el('p', {}, ['Helper path: ', el('code', { text: `${root}/_control/scripts/runs/render-create-run.js` })]));

  const selectionSelect = el('select');
  selectionSelect.style.width = '100%';
  if (!selections.length) {
    selectionSelect.appendChild(el('option', { text: 'No selection manifests found.' }));
    selectionSelect.disabled = true;
  } else {
    const active = newestActiveSelection(app, selections);
    if (active) selectionSelect.appendChild(el('option', { value: active.file, text: selectionOptionText(active, 'Active/newest: ') }));
    selectionSelect.appendChild(el('option', { value: '', text: '──────── saved selections ────────' }));
    for (const sel of selections) selectionSelect.appendChild(el('option', { value: sel.file, text: selectionOptionText(sel) }));
  }

  const planSelect = el('select');
  planSelect.style.width = '100%';
  if (!plans.length) {
    planSelect.appendChild(el('option', { text: 'No saved plans found.' }));
    planSelect.disabled = true;
  } else {
    for (const plan of plans) planSelect.appendChild(el('option', { value: plan.file, text: planOptionText(plan) }));
  }

  const label = el('input', { type: 'text', placeholder: 'Optional run label' });
  label.style.width = '100%';

  const summary = el('p', { text: 'Load a selection and plan to preview the run.' });
  const promptBox = el('div');
  const planBox = el('div');
  const savedPath = el('code', { text: '' });

  function selectedPlan() {
    return plans.find((p) => p.file === planSelect.value)?.record || null;
  }

  function refreshPreview() {
    promptBox.innerHTML = '';
    planBox.innerHTML = '';
    savedPath.textContent = '';

    if (!selectionSelect.value) return;
    loadedSelection = selectionSummary(app, selectionSelect.value);
    summary.textContent = statusText(loadedSelection);

    promptBox.appendChild(el('h3', { text: 'Prompts' }));
    renderPromptTable(promptBox, loadedSelection.items);

    const plan = selectedPlan();
    planBox.appendChild(el('h3', { text: 'Plan steps' }));
    if (plan) {
      planBox.appendChild(el('p', { text: `${plan.label || plan.slug} — ${plan.slug}` }));
      renderPlanTable(planBox, plan);
    } else {
      planBox.appendChild(el('p', { text: 'No plan selected.' }));
    }
  }

  selectionSelect.addEventListener('change', refreshPreview);
  planSelect.addEventListener('change', refreshPreview);

  const saveBtn = button('Save Run Manifest', () => {
    try {
      if (!loadedSelection) refreshPreview();
      const plan = selectedPlan();
      const manifest = buildRunManifest({ app, label: label.value, selection: loadedSelection, plan });
      const files = saveRunManifest(app, manifest);
      savedPath.textContent = files.currentFile;
      new Notice(`Saved run manifest: ${manifest.label} (${manifest.call_count} calls)`);
    } catch (err) {
      new Notice(`Run manifest failed: ${err.message}`);
      console.error(err);
    }
  });
  const copyBtn = button('Copy Current Path', () => savedPath.textContent && copyText(savedPath.textContent));

  const controls = el('div');
  controls.style.display = 'grid';
  controls.style.gridTemplateColumns = '1fr';
  controls.style.gap = '0.5rem';
  controls.append(
    el('label', {}, ['Prompt selection', selectionSelect]),
    el('label', {}, ['Saved plan', planSelect]),
    el('label', {}, ['Run label', label]),
    summary
  );
  const saveRow = el('div');
  saveRow.style.display = 'flex';
  saveRow.style.gap = '0.5rem';
  saveRow.style.alignItems = 'center';
  saveRow.append(saveBtn, copyBtn, savedPath);
  controls.appendChild(saveRow);

  container.append(controls, promptBox, planBox);
  if (selections.length && plans.length) refreshPreview();
}

module.exports = { renderCreateRun };
