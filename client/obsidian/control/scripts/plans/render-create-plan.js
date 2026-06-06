const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const {
  controlRoots,
  loadRegistrySnapshot,
  loadControlSnapshot,
  snapshotList,
} = require('../lib/control-loader.js');
const {
  buildPlanRecord,
  savePlanRecord,
  listPlanRecords,
  loadPlanRecord,
  deletePlanRecord,
} = require('./plan-store.js');

const STEP_KINDS = [
  { value: 'llm', label: 'LLM call' },
  { value: 'script', label: 'Script' },
  { value: 'rag', label: 'RAG' },
];

function normalizeKind(value) {
  return String(value || '').trim().toLowerCase();
}

function sortByLabel(records) {
  return [...records].sort((a, b) => {
    const la = String(a.label || a.slug || a.key || '');
    const lb = String(b.label || b.slug || b.key || '');
    const cmp = la.localeCompare(lb);
    if (cmp) return cmp;
    return String(a.slug || a.key || '').localeCompare(String(b.slug || b.key || ''));
  });
}

function optionText(record) {
  const id = record.slug || record.key || '';
  const kind = record.kind ? ` [${normalizeKind(record.kind)}]` : '';
  const type = record.type && !record.kind ? ` [${normalizeKind(record.type)}]` : '';
  const dirty = record.repo_state && record.repo_state !== 'clean' ? ' [dirty]' : '';
  const noCommit = record.has_prior_commit === false ? ' [no commit]' : '';
  const source = record.source ? `[${record.source}] ` : '';
  const identity = record.identity ? ` (${record.identity})` : '';
  return `${source}${record.label || id} — ${id}${kind}${type}${identity}${dirty}${noCommit}`;
}

function planOptionText(record) {
  const bad = record.read_error ? ' [read error]' : '';
  const count = Number.isFinite(record.step_count) ? ` — ${record.step_count} step(s)` : '';
  const changed = record.modified || record.file_mtime || record.created || '';
  return `${record.label || record.slug} — ${record.slug}${count}${changed ? ` (${changed})` : ''}${bad}`;
}

function selectFor(records, placeholder, valueField = 'slug') {
  const select = el('select');
  select.style.width = '100%';
  select.appendChild(el('option', { value: '', text: placeholder }));
  for (const rec of records) {
    const value = rec[valueField] || rec.slug || rec.key;
    const option = el('option', { value, text: optionText(rec) });
    select.appendChild(option);
  }
  return select;
}

function selectedRecord(select, records, valueField = 'slug') {
  return records.find((r) => (r[valueField] || r.slug || r.key) === select.value) || null;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    new Notice('Copied.');
  } catch {
    new Notice('Clipboard copy failed.');
  }
}

function hydrateControl(saved, liveRecords, valueField = 'slug') {
  if (!saved) return null;
  const savedId = saved[valueField] || saved.slug || saved.key;
  return liveRecords.find((record) => (record[valueField] || record.slug || record.key) === savedId) || saved;
}

function isScriptEngine(engine) {
  const key = String(engine?.key || '').toLowerCase();
  const kind = normalizeKind(engine?.kind || engine?.type);
  const label = String(engine?.label || '').toLowerCase();
  return (
    kind === 'script'
    || kind === 'scripts'
    || kind === 'local'
    || key.includes('scripts')
    || key.includes('local')
    || label === 'scripts'
    || label === 'local'
  );
}

function isRagEngine(engine) {
  const key = String(engine?.key || '').toLowerCase();
  const kind = normalizeKind(engine?.kind || engine?.type);
  const label = String(engine?.label || '').toLowerCase();
  return kind === 'rag' || key.includes('rag') || label.includes('rag');
}

function findScriptEngine(engines) {
  return engines.find(isScriptEngine) || null;
}

function findRagEngine(engines) {
  return engines.find(isRagEngine) || null;
}

function llmEngines(engines) {
  return engines.filter((engine) => !isScriptEngine(engine) && !isRagEngine(engine));
}

function inferStepKind(step) {
  const savedKind = normalizeKind(step.kind || step.step_kind || step.type);
  if (savedKind === 'llm' || savedKind === 'script' || savedKind === 'rag') return savedKind;
  if (step.script) return 'script';
  if (step.rag_profile) return 'rag';
  return 'llm';
}

function emptyStep(kind, index, { engines }) {
  const scriptEngine = findScriptEngine(engines);
  const ragEngine = findRagEngine(engines);
  const defaultLlmEngine = llmEngines(engines)[0] || engines[0] || null;
  const step = {
    kind,
    label: `Step ${index}`,
    engine: null,
    model: '',
    script: null,
    rag_profile: null,
    argsJson: '{}',
    instructions: [],
  };
  if (kind === 'script') step.engine = scriptEngine;
  else if (kind === 'rag') step.engine = ragEngine;
  else step.engine = defaultLlmEngine;
  return step;
}

function coerceStepKind(step, kind, { engines }) {
  step.kind = kind;
  if (kind === 'script') {
    step.engine = findScriptEngine(engines);
    step.rag_profile = null;
    step.model = '';
  } else if (kind === 'rag') {
    step.engine = findRagEngine(engines);
    step.script = null;
    step.model = '';
  } else {
    step.engine = llmEngines(engines).find((engine) => engine.key === step.engine?.key) || llmEngines(engines)[0] || step.engine || null;
    step.script = null;
    step.rag_profile = null;
  }
}

function planToScreenSteps(plan, { engines, instructions, scripts, ragProfiles }) {
  return (plan.steps || []).map((step, index) => {
    const kind = inferStepKind(step);
    const screenStep = {
      kind,
      label: step.label || `Step ${index + 1}`,
      engine: hydrateControl(step.engine, engines, 'key'),
      script: hydrateControl(step.script, scripts, 'key'),
      rag_profile: hydrateControl(step.rag_profile, ragProfiles, 'key'),
      model: step.model || step.args?.model || '',
      argsJson: JSON.stringify(step.args || {}, null, 2),
      instructions: (step.instructions || step.instruction_slugs || [])
        .map((ins) => hydrateControl(typeof ins === 'string' ? { slug: ins } : ins, instructions, 'slug'))
        .filter(Boolean),
    };
    coerceStepKind(screenStep, kind, { engines });
    return screenStep;
  });
}

function renderKindRadios({ currentKind, onChange, name }) {
  const wrapper = el('span');
  wrapper.style.display = 'inline-flex';
  wrapper.style.gap = '0.75rem';
  wrapper.style.alignItems = 'center';
  for (const item of STEP_KINDS) {
    const input = el('input', { type: 'radio', name, value: item.value });
    input.checked = item.value === currentKind;
    input.addEventListener('change', () => {
      if (input.checked) onChange(item.value);
    });
    const label = el('label');
    label.style.display = 'inline-flex';
    label.style.gap = '0.25rem';
    label.style.alignItems = 'center';
    label.append(input, document.createTextNode(item.label));
    wrapper.appendChild(label);
  }
  return wrapper;
}

function renderInstructionPicker({ step, instructions, redraw }) {
  const wrapper = el('div');
  const insSelect = selectFor(instructions, 'Add uploaded instruction', 'slug');
  const insList = el('ul');

  function redrawInstructions() {
    insList.innerHTML = '';
    if (!step.instructions.length) {
      insList.appendChild(el('li', { text: 'No instructions selected.' }));
      return;
    }
    step.instructions.forEach((ins, insIndex) => {
      const li = el('li');
      li.appendChild(el('code', { text: ins.slug || ins.key }));
      li.appendChild(document.createTextNode(` — ${ins.label || ins.identity || ''} `));
      li.appendChild(button('↑', () => {
        if (insIndex === 0) return;
        [step.instructions[insIndex - 1], step.instructions[insIndex]] = [step.instructions[insIndex], step.instructions[insIndex - 1]];
        redraw();
      }));
      li.appendChild(button('↓', () => {
        if (insIndex >= step.instructions.length - 1) return;
        [step.instructions[insIndex + 1], step.instructions[insIndex]] = [step.instructions[insIndex], step.instructions[insIndex + 1]];
        redraw();
      }));
      li.appendChild(button('Remove', () => {
        step.instructions.splice(insIndex, 1);
        redraw();
      }));
      insList.appendChild(li);
    });
  }

  const addIns = button('Add Instruction', () => {
    const rec = selectedRecord(insSelect, instructions, 'slug');
    if (!rec) return;
    if (!step.instructions.some((i) => i.slug === rec.slug)) step.instructions.push(rec);
    insSelect.value = '';
    redraw();
  });

  wrapper.appendChild(el('label', {}, ['Instructions', insSelect]));
  wrapper.append(addIns, insList);
  redrawInstructions();
  return wrapper;
}

function renderProviderPicker({ step, engines }) {
  const providers = llmEngines(engines);
  const engineSelect = selectFor(providers, providers.length ? 'Choose provider/engine' : 'No LLM engines in registry snapshot', 'key');
  engineSelect.value = step.engine?.key || '';
  engineSelect.addEventListener('change', () => {
    step.engine = selectedRecord(engineSelect, providers, 'key');
  });
  return el('label', {}, ['Provider / engine', engineSelect]);
}

function renderModelInput(step) {
  const model = el('input', { type: 'text', placeholder: 'Model, e.g. gpt-5.5-mini', value: step.model || '' });
  model.style.width = '100%';
  model.addEventListener('input', () => { step.model = model.value; });
  return el('label', {}, ['Model', model]);
}

function renderScriptPicker({ step, scripts }) {
  const scriptSelect = selectFor(scripts, scripts.length ? 'Choose script' : 'No scripts in registry snapshot', 'key');
  scriptSelect.value = step.script?.key || '';
  scriptSelect.addEventListener('change', () => {
    step.script = selectedRecord(scriptSelect, scripts, 'key');
  });
  return el('label', {}, ['Script', scriptSelect]);
}

function renderRagPicker({ step, ragProfiles }) {
  const ragSelect = selectFor(ragProfiles, ragProfiles.length ? 'Choose RAG profile' : 'No RAG profiles in registry snapshot', 'key');
  ragSelect.value = step.rag_profile?.key || '';
  ragSelect.addEventListener('change', () => {
    step.rag_profile = selectedRecord(ragSelect, ragProfiles, 'key');
  });
  return el('label', {}, ['RAG profile', ragSelect]);
}

function renderArgsEditor(step, labelText = 'Optional args JSON') {
  const args = el('textarea', { placeholder: '{}', value: step.argsJson || '{}' });
  args.style.width = '100%';
  args.style.minHeight = '4rem';
  args.style.fontFamily = 'var(--font-monospace)';
  args.addEventListener('input', () => { step.argsJson = args.value; });
  return el('label', {}, [labelText, args]);
}

function renderStepSpecificControls({ step, engines, scripts, instructions, ragProfiles, redraw }) {
  const wrapper = el('div');
  if (step.kind === 'script') {
    const engine = step.engine || findScriptEngine(engines);
    step.engine = engine;
    wrapper.appendChild(el('p', {}, ['Engine: ', el('code', { text: engine?.label || engine?.key || 'script engine not found' })]));
    wrapper.appendChild(renderScriptPicker({ step, scripts }));
    wrapper.appendChild(renderArgsEditor(step, 'Optional script args JSON'));
    return wrapper;
  }

  if (step.kind === 'rag') {
    const engine = step.engine || findRagEngine(engines);
    step.engine = engine;
    wrapper.appendChild(el('p', {}, ['Engine: ', el('code', { text: engine?.label || engine?.key || 'RAG engine not found' })]));
    wrapper.appendChild(renderRagPicker({ step, ragProfiles }));
    wrapper.appendChild(renderInstructionPicker({ step, instructions, redraw }));
    wrapper.appendChild(renderArgsEditor(step, 'Optional RAG args JSON'));
    return wrapper;
  }

  wrapper.appendChild(renderProviderPicker({ step, engines }));
  wrapper.appendChild(renderModelInput(step));
  wrapper.appendChild(renderInstructionPicker({ step, instructions, redraw }));
  wrapper.appendChild(renderArgsEditor(step, 'Optional LLM args JSON'));
  return wrapper;
}

function renderStepEditor({ stepsBox, engines, scripts, instructions, ragProfiles, steps }) {
  function redraw() {
    renderStepEditor({ stepsBox, engines, scripts, instructions, ragProfiles, steps });
  }

  stepsBox.innerHTML = '';
  if (!steps.length) {
    stepsBox.appendChild(el('p', { text: 'No steps on the screen yet.' }));
    return;
  }

  steps.forEach((step, index) => {
    if (!step.kind) coerceStepKind(step, inferStepKind(step), { engines });

    const card = el('div');
    card.style.border = '1px solid var(--background-modifier-border)';
    card.style.borderRadius = '8px';
    card.style.padding = '0.75rem';
    card.style.marginBottom = '0.75rem';

    const title = el('input', { type: 'text', value: step.label || `Step ${index + 1}` });
    title.style.width = '100%';
    title.addEventListener('input', () => { step.label = title.value; });

    const kindRow = el('div');
    kindRow.style.display = 'flex';
    kindRow.style.gap = '0.75rem';
    kindRow.style.alignItems = 'center';
    kindRow.style.flexWrap = 'wrap';
    kindRow.append(
      el('strong', { text: 'Step type' }),
      renderKindRadios({
        currentKind: step.kind,
        name: `step-kind-${index}`,
        onChange: (kind) => {
          coerceStepKind(step, kind, { engines });
          redraw();
        },
      })
    );

    const controls = el('div');
    controls.style.display = 'flex';
    controls.style.gap = '0.5rem';
    controls.style.flexWrap = 'wrap';
    controls.append(
      button('↑', () => {
        if (index === 0) return;
        [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]];
        redraw();
      }),
      button('↓', () => {
        if (index >= steps.length - 1) return;
        [steps[index + 1], steps[index]] = [steps[index], steps[index + 1]];
        redraw();
      }),
      button('Delete Step', () => {
        steps.splice(index, 1);
        redraw();
      })
    );

    card.appendChild(el('h3', { text: `Step ${index + 1}` }));
    card.appendChild(el('label', {}, ['Step label', title]));
    card.appendChild(kindRow);
    card.appendChild(renderStepSpecificControls({ step, engines, scripts, instructions, ragProfiles, redraw }));
    card.appendChild(controls);
    stepsBox.appendChild(card);
  });
}

async function renderCreatePlan({ app, container }) {
  clear(container);
  const root = vaultRoot(app);
  const roots = controlRoots(app);
  const registrySnapshot = loadRegistrySnapshot();
  const controlSnapshot = loadControlSnapshot();
  const engines = sortByLabel(snapshotList(registrySnapshot.data, 'engines'));
  const scripts = sortByLabel(snapshotList(registrySnapshot.data, 'local_scripts'));
  const ragProfiles = sortByLabel(snapshotList(registrySnapshot.data, 'rag_profiles'));
  const instructions = sortByLabel(snapshotList(controlSnapshot.data, 'instructions'));
  const steps = [];
  let loadedPlan = null;
  let newStepKind = 'llm';

  container.appendChild(el('h2', { text: 'Define Plan' }));
  container.appendChild(el('p', { text: 'A plan is a reusable ordered set of processing steps. Pick a step type first; the screen then shows only the relevant provider, model, script, RAG, instruction, and args fields.' }));
  container.appendChild(el('p', {}, ['Helper path: ', el('code', { text: `${root}/_control/scripts/plans/render-create-plan.js` })]));

  const existingPlansBox = el('div');
  const existingSelect = el('select');
  existingSelect.style.width = '100%';
  const currentPlan = el('code', { text: 'new unsaved plan' });

  function refreshExistingPlans(selectedSlug = '') {
    const plans = listPlanRecords(app);
    existingSelect.innerHTML = '';
    existingSelect.appendChild(el('option', { value: '', text: plans.length ? 'Choose existing plan' : 'No saved plans found' }));
    for (const plan of plans) {
      existingSelect.appendChild(el('option', { value: plan.slug, text: planOptionText(plan) }));
    }
    if (selectedSlug) existingSelect.value = selectedSlug;
  }

  const label = el('input', { type: 'text', placeholder: 'Plan label, e.g. Fact Check' });
  label.style.width = '100%';
  const description = el('textarea', { placeholder: 'Optional description' });
  description.style.width = '100%';
  description.style.minHeight = '5rem';

  const registryText = registrySnapshot.data
    ? `Registry snapshot: ${registrySnapshot.command} ${registrySnapshot.args.join(' ')}`
    : `Registry snapshot failed: ${registrySnapshot.error || 'unknown error'}${registrySnapshot.stderr ? ` — ${registrySnapshot.stderr}` : ''}`;
  const controlText = controlSnapshot.data
    ? `Control snapshot: ${controlSnapshot.command} ${controlSnapshot.args.join(' ')}`
    : `Control snapshot failed: ${controlSnapshot.error || 'unknown error'}${controlSnapshot.stderr ? ` — ${controlSnapshot.stderr}` : ''}`;
  const status = el('p', {
    text: `${instructions.length} instruction(s), ${llmEngines(engines).length} LLM engine(s), ${scripts.length} script(s), ${ragProfiles.length} RAG profile(s) found. ${controlText}. ${registryText}`,
  });
  const rootsText = el('p', { text: `Control roots available for local editing: ${roots.join(', ')}` });
  const stepsBox = el('div');
  const savedPath = el('code', { text: '' });

  function redrawSteps() {
    renderStepEditor({ stepsBox, engines, scripts, instructions, ragProfiles, steps });
  }

  function clearScreen() {
    loadedPlan = null;
    existingSelect.value = '';
    currentPlan.textContent = 'new unsaved plan';
    savedPath.textContent = '';
    label.value = '';
    description.value = '';
    steps.splice(0, steps.length);
    redrawSteps();
  }

  function loadSelectedPlan() {
    const slug = existingSelect.value;
    if (!slug) return;
    try {
      const plan = loadPlanRecord(app, slug);
      loadedPlan = plan;
      currentPlan.textContent = `${plan.slug} (${plan.file || 'saved plan'})`;
      savedPath.textContent = plan.file || '';
      label.value = plan.label || '';
      description.value = plan.description || '';
      steps.splice(0, steps.length, ...planToScreenSteps(plan, { engines, instructions, scripts, ragProfiles }));
      redrawSteps();
      new Notice(`Loaded plan: ${plan.label || plan.slug}`);
    } catch (err) {
      new Notice(`Load plan failed: ${err.message}`);
      console.error(err);
    }
  }

  function snapshotPayload(existing = null, forceSlug = null) {
    return buildPlanRecord({
      app,
      label: label.value,
      description: description.value,
      steps,
      existing,
      force_slug: forceSlug,
      registry_snapshot: {
        command: registrySnapshot.command,
        args: registrySnapshot.args,
        schema_version: registrySnapshot.data?.schema_version || null,
        sources: registrySnapshot.data?.sources || null,
      },
      control_snapshot: {
        command: controlSnapshot.command,
        args: controlSnapshot.args,
        schema_version: controlSnapshot.data?.schema_version || null,
        source: controlSnapshot.data?.source || null,
      },
    });
  }

  function saveRecord(record) {
    const file = savePlanRecord(app, record);
    savedPath.textContent = file;
    loadedPlan = { ...record, file };
    currentPlan.textContent = `${record.slug} (${file})`;
    refreshExistingPlans(record.slug);
    const warn = record.preflight.warnings.length ? ` (${record.preflight.warnings.join('; ')})` : '';
    new Notice(`Saved plan: ${record.label}${warn}`);
  }

  const loadBtn = button('Modify Selected Plan', loadSelectedPlan);
  const newBtn = button('New Blank Plan', clearScreen);
  const deleteBtn = button('Delete Selected Plan', () => {
    const slug = existingSelect.value || loadedPlan?.slug;
    if (!slug) {
      new Notice('Choose a saved plan to delete.');
      return;
    }
    if (!confirm(`Delete plan ${slug}?`)) return;
    try {
      const file = deletePlanRecord(app, slug);
      if (loadedPlan?.slug === slug) clearScreen();
      refreshExistingPlans('');
      new Notice(`Deleted plan: ${file}`);
    } catch (err) {
      new Notice(`Delete plan failed: ${err.message}`);
      console.error(err);
    }
  });

  const addStep = button('Add Step', () => {
    steps.push(emptyStep(newStepKind, steps.length + 1, { engines }));
    redrawSteps();
  });

  const saveChangesBtn = button('Save Changes to Loaded Plan', () => {
    if (!loadedPlan?.slug) {
      new Notice('Load a plan first, or use Save Screen as New Plan.');
      return;
    }
    try {
      saveRecord(snapshotPayload(loadedPlan, loadedPlan.slug));
    } catch (err) {
      new Notice(`Save plan failed: ${err.message}`);
      console.error(err);
    }
  });

  const saveNewBtn = button('Save Screen as New Plan', () => {
    try {
      saveRecord(snapshotPayload(null, null));
    } catch (err) {
      new Notice(`Save new plan failed: ${err.message}`);
      console.error(err);
    }
  });
  const copyBtn = button('Copy Saved Path', () => savedPath.textContent && copyText(savedPath.textContent));

  refreshExistingPlans('');
  const existingRow = el('div');
  existingRow.style.display = 'flex';
  existingRow.style.gap = '0.5rem';
  existingRow.style.alignItems = 'center';
  existingRow.style.flexWrap = 'wrap';
  existingRow.append(loadBtn, newBtn, deleteBtn, el('span', {}, ['Current: ', currentPlan]));
  existingPlansBox.appendChild(el('label', {}, ['Existing plans', existingSelect]));
  existingPlansBox.appendChild(existingRow);

  const addStepRow = el('div');
  addStepRow.style.display = 'flex';
  addStepRow.style.gap = '0.75rem';
  addStepRow.style.alignItems = 'center';
  addStepRow.style.flexWrap = 'wrap';
  addStepRow.append(
    addStep,
    renderKindRadios({
      currentKind: newStepKind,
      name: 'new-step-kind',
      onChange: (kind) => { newStepKind = kind; },
    })
  );

  container.appendChild(existingPlansBox);
  container.appendChild(el('label', {}, ['Plan label', label]));
  container.appendChild(el('label', {}, ['Description', description]));
  container.appendChild(status);
  container.appendChild(rootsText);
  container.appendChild(addStepRow);
  container.appendChild(stepsBox);
  const row = el('div');
  row.style.display = 'flex';
  row.style.gap = '0.5rem';
  row.style.alignItems = 'center';
  row.style.flexWrap = 'wrap';
  row.append(saveChangesBtn, saveNewBtn, copyBtn, savedPath);
  container.appendChild(row);

  if (!registrySnapshot.data) {
    new Notice(`Define Plan: asc registry snapshot failed: ${registrySnapshot.error || 'unknown error'}`);
  }
  if (!controlSnapshot.data) {
    new Notice(`Define Plan: asc control snapshot failed: ${controlSnapshot.error || 'unknown error'}`);
  }
  if (engines.length || scripts.length || ragProfiles.length) addStep.click();
  else redrawSteps();
}

module.exports = { renderCreatePlan };
