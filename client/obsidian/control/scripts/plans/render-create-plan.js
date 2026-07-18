const { spawnSync } = require('child_process');
const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const { snapshotList } = require('../lib/control-loader.js');
const { buildPlanRecord } = require('./plan-record.js');
const { callFeeder } = require('../lib/feeder-ipc.js');
const { createInternalLink } = require('../lib/internal-link.js');
const { getFrontmatterEntry } = require('../lib/frontmatter.js');
const { normalizeWikiTarget } = require('../lib/wikilinks.js');

const STEP_KINDS = [
  { value: 'llm', label: 'LLM call' },
  { value: 'script', label: 'Script' },
  { value: 'rag', label: 'RAG' },
];

/*
 * ASC / FEEDER TRANSPORT BOUNDARY
 * --------------------------------
 * Read-only catalogs come directly from the existing ASC snapshot commands.
 * Full-plan retrieval and plan upload go through feeder IPC.
 */
const ZSH = '/usr/bin/zsh';
const sessionPlanStore = new Map();

function ascSnapshot(group, cwd) {
  const command = `asc ${group} snapshot`;
  const result = spawnSync(ZSH, ['-lic', command], {
    cwd,
    encoding: 'utf8',
    maxBuffer: 16 * 1024 * 1024,
    timeout: 30000,
    env: process.env,
  });

  if (result.error) {
    throw new Error(`${command} could not start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || '').trim();
    throw new Error(`${command} failed: ${detail || `exit status ${result.status}`}`);
  }

  const stdout = String(result.stdout || '').trim();
  if (!stdout) throw new Error(`${command} returned no JSON.`);

  try {
    return JSON.parse(stdout);
  } catch (error) {
    throw new Error(`${command} returned invalid JSON: ${error.message}`);
  }
}

function pipelinePlans(controlSnapshot) {
  return snapshotList(controlSnapshot, 'plans')
    .map((record) => {
      const ttl = Number(record.ttl);
      return {
        ...record,
        ttl: Number.isFinite(ttl) ? ttl : -2,
        label: record.label || record.slug,
      };
    })
    .filter((record) => record.ttl !== -2);
}

async function feederListPlans(controlSnapshot) {
  const bySlug = new Map();
  for (const record of pipelinePlans(controlSnapshot)) {
    bySlug.set(record.record_identity || record.slug, record);
  }
  for (const [slug, record] of sessionPlanStore.entries()) {
    bySlug.set(slug, { ...record, ttl: Number.POSITIVE_INFINITY });
  }

  return [...bySlug.values()].sort((a, b) => {
    const at = Number(a.ttl);
    const bt = Number(b.ttl);
    if (at !== bt) return bt - at;
    return String(a.label || planSlug(a)).localeCompare(String(b.label || planSlug(b)));
  });
}

function materializePlan(record) {
  if (!record || typeof record !== 'object') {
    throw new Error('Feeder returned an invalid plan record.');
  }

  const content = record.payload;
  if (content && typeof content === 'object' && !Array.isArray(content)) {
    return { ...record, ...content };
  }
  return record;
}

async function feederLoadPlan(app, slug) {
  if (!slug) throw new Error('Select an uploaded plan to load.');
  return materializePlan(await callFeeder(app, 'plan.load', { slug }));
}

async function feederUploadPlan(app, record, instructionSets) {
  return callFeeder(app, 'plan.save', { record, instruction_sets: instructionSets });
}

async function feederListInstructions(app) {
  return callFeeder(app, 'instructions.catalog', { include_pipeline: true });
}

function normalizeKind(value) {
  return String(value || '').trim().toLowerCase();
}

function planSlug(record) {
  return record?.record_identity || record?.slug || '';
}

function sortByLabel(records) {
  return [...records].sort((a, b) => {
    const left = String(a.label || a.slug || a.key || '');
    const right = String(b.label || b.slug || b.key || '');
    return left.localeCompare(right);
  });
}

function optionText(record) {
  const id = record.record_identity || record.slug || record.key || '';
  return `${record.label || id} — ${id}`;
}

function selectFor(records, placeholder, valueField = 'key') {
  const select = el('select');
  select.style.width = '100%';
  select.appendChild(el('option', { value: '', text: placeholder }));
  for (const record of records) {
    const value = record[valueField] || record.slug || record.key;
    select.appendChild(el('option', { value, text: optionText(record) }));
  }
  return select;
}

function selectedRecord(select, records, valueField = 'key') {
  return records.find((record) => (
    record[valueField] || record.slug || record.key
  ) === select.value) || null;
}

function hydrate(saved, records, valueField = 'key') {
  if (!saved) return null;
  const savedValue = typeof saved === 'string'
    ? saved
    : saved[valueField] || saved.slug || saved.key;
  return records.find((record) => (
    record[valueField] || record.slug || record.key
  ) === savedValue) || { [valueField]: savedValue, key: savedValue, slug: savedValue };
}

function engineKind(record) {
  return normalizeKind(record?.kind || record?.type || record?.key);
}

function isScriptEngine(record) {
  return engineKind(record).includes('script');
}

function isRagEngine(record) {
  return engineKind(record).includes('rag');
}

function llmEngines(engines) {
  return engines.filter((record) => !isScriptEngine(record) && !isRagEngine(record));
}

function modelsForEngine(models, engine) {
  if (!engine) return [];
  const engineKey = String(engine.key || '');
  return models.filter((model) => {
    const owner = String(model.engine || model.engine_key || model.provider || model.provider_key || '');
    return !owner || owner === engineKey;
  });
}

function emptyStep(kind, index, catalogs) {
  return {
    index,
    kind,
    label: `Step ${index}`,
    engine: kind === 'llm' ? (llmEngines(catalogs.engines)[0] || null) : null,
    model: null,
    script: null,
    rag_profile: null,
    instruction: null,
    argsJson: '{}',
  };
}

function coerceStepKind(step, kind, catalogs) {
  step.kind = kind;
  step.engine = kind === 'llm' ? (llmEngines(catalogs.engines)[0] || null) : null;
  step.model = null;
  step.script = null;
  step.rag_profile = null;
}

function planStepEntries(steps) {
  if (Array.isArray(steps)) return steps.map((step, index) => [index + 1, step]);
  return Object.entries(steps || {})
    .map(([key, step]) => [Number(key), step])
    .filter(([number, step]) => Number.isInteger(number) && number > 0 && step)
    .sort(([a], [b]) => a - b);
}

function planToScreenSteps(plan, catalogs) {
  return planStepEntries(plan.steps).map(([number, step]) => {
    const kind = normalizeKind(step.kind || step.type || (step.script ? 'script' : step.rag_profile ? 'rag' : 'llm'));
    const instructionSlug = step.instruction;
    return {
      index: number,
      kind,
      label: step.label || `Step ${number}`,
      engine: hydrate(step.engine, catalogs.engines),
      model: hydrate(step.model || step.args?.model, catalogs.models),
      script: hydrate(step.script, catalogs.scripts),
      rag_profile: hydrate(step.rag_profile, catalogs.ragProfiles),
      instruction: hydrate(instructionSlug, catalogs.instructions, 'slug'),
      argsJson: JSON.stringify(step.args || {}, null, 2),
    };
  });
}

function renderKindRadios({ currentKind, onChange, name }) {
  const wrapper = el('span');
  wrapper.style.display = 'inline-flex';
  wrapper.style.gap = '0.75rem';
  for (const item of STEP_KINDS) {
    const input = el('input', { type: 'radio', name, value: item.value });
    input.checked = item.value === currentKind;
    input.addEventListener('change', () => input.checked && onChange(item.value));
    wrapper.appendChild(el('label', {}, [input, document.createTextNode(item.label)]));
  }
  return wrapper;
}

function renderArgsEditor(step) {
  const textarea = el('textarea', { value: step.argsJson || '{}', placeholder: '{}' });
  textarea.style.width = '100%';
  textarea.style.minHeight = '4rem';
  textarea.style.fontFamily = 'var(--font-monospace)';
  textarea.addEventListener('input', () => { step.argsJson = textarea.value; });
  return el('label', {}, ['Optional args JSON', textarea]);
}

function renderInstructionPicker(app, step, instructions) {
  const wrapper = el('div');
  const select = selectFor(instructions, 'No instruction', 'slug');
  const linkBox = el('div');
  linkBox.style.marginTop = '0.25rem';

  function redrawLink() {
    linkBox.innerHTML = '';
    const record = step.instruction;
    if (!record?.path) return;
    linkBox.appendChild(document.createTextNode('Selected: '));
    createInternalLink(linkBox, app, record.path, `[[${record.label || record.slug}]]`);
  }

  select.value = step.instruction?.slug || step.instruction?.key || '';
  select.addEventListener('change', () => {
    step.instruction = selectedRecord(select, instructions, 'slug');
    redrawLink();
  });
  wrapper.append(select, linkBox);
  redrawLink();
  return el('label', {}, ['Instruction', wrapper]);
}

function frontmatterLinks(value) {
  const values = Array.isArray(value) ? value : [value];
  return values
    .map((item) => normalizeWikiTarget(item))
    .filter(Boolean);
}

function instructionComponent(app, file, sourcePath) {
  const slug = String(getFrontmatterEntry(app, file, 'slug') || '').trim();
  if (!slug) throw new Error(`${file.path}: referenced instruction component has no slug.`);
  return {
    slug,
    path: file.path,
    source_path: file.path,
    abspath: require('node:path').resolve(vaultRoot(app), file.path),
  };
}

function resolveInstructionDependencies(app, record) {
  if (!record?.path || !record?.abspath) {
    throw new Error(`Instruction ${record?.slug || '<unknown>'} has no local source file.`);
  }
  const taskFile = app.vault.getAbstractFileByPath(record.path);
  if (!taskFile) throw new Error(`Instruction file not found in vault: ${record.path}`);

  const roleTargets = frontmatterLinks(getFrontmatterEntry(app, taskFile, 'role'));
  const contextTargets = frontmatterLinks(getFrontmatterEntry(app, taskFile, 'context'));
  if (roleTargets.length !== 1) {
    throw new Error(`${record.path}: instruction frontmatter requires exactly one role wikilink.`);
  }
  if (!contextTargets.length) {
    throw new Error(`${record.path}: instruction frontmatter requires at least one context wikilink.`);
  }

  const roleFile = app.metadataCache.getFirstLinkpathDest(roleTargets[0], record.path);
  if (!roleFile) throw new Error(`${record.path}: unresolved role wikilink: ${roleTargets[0]}`);
  const contextFiles = contextTargets.map((target) => {
    const file = app.metadataCache.getFirstLinkpathDest(target, record.path);
    if (!file) throw new Error(`${record.path}: unresolved context wikilink: ${target}`);
    return file;
  });

  const task = instructionComponent(app, taskFile, record.path);
  const role = instructionComponent(app, roleFile, record.path);
  const contexts = contextFiles.map((file) => instructionComponent(app, file, record.path));
  return { task, role, contexts };
}

function prepareInstructionDependencies(app, steps) {
  const components = new Map();
  for (const step of steps) {
    if (!step.instruction) continue;

    const resolved = resolveInstructionDependencies(app, step.instruction);
    for (const component of [resolved.task, resolved.role, ...resolved.contexts]) {
      components.set(component.slug, component);
    }
  }
  return [...components.values()];
}

function renderStepEditor({ app, stepsBox, steps, catalogs }) {
  const redraw = () => renderStepEditor({ app, stepsBox, steps, catalogs });
  stepsBox.innerHTML = '';

  if (!steps.length) {
    stepsBox.appendChild(el('p', { text: 'No steps yet.' }));
    return;
  }

  steps.forEach((step, index) => {
    const card = el('div');
    card.style.border = '1px solid var(--background-modifier-border)';
    card.style.borderRadius = '8px';
    card.style.padding = '0.75rem';
    card.style.marginBottom = '0.75rem';

    const labelInput = el('input', { type: 'text', value: step.label || `Step ${index + 1}` });
    labelInput.style.width = '100%';
    labelInput.addEventListener('input', () => { step.label = labelInput.value; });

    card.append(
      el('h3', { text: `Step ${index + 1}` }),
      el('label', {}, ['Step label', labelInput]),
      renderKindRadios({
        currentKind: step.kind,
        name: `step-kind-${index}`,
        onChange: (kind) => {
          coerceStepKind(step, kind, catalogs);
          redraw();
        },
      })
    );

    if (step.kind === 'llm') {
      const providers = llmEngines(catalogs.engines);
      const engineSelect = selectFor(providers, 'Choose provider/engine');
      engineSelect.value = step.engine?.key || '';
      engineSelect.addEventListener('change', () => {
        step.engine = selectedRecord(engineSelect, providers);
        step.model = null;
        redraw();
      });
      card.appendChild(el('label', {}, ['Provider / engine', engineSelect]));

      const modelChoices = modelsForEngine(catalogs.models, step.engine);
      const modelSelect = selectFor(modelChoices, 'Choose model');
      modelSelect.value = step.model?.key || '';
      modelSelect.addEventListener('change', () => {
        step.model = selectedRecord(modelSelect, modelChoices);
      });
      card.appendChild(el('label', {}, ['Model', modelSelect]));
      card.appendChild(renderInstructionPicker(app, step, catalogs.instructions));
    } else if (step.kind === 'script') {
      const scriptSelect = selectFor(catalogs.scripts, 'Choose script');
      scriptSelect.value = step.script?.key || '';
      scriptSelect.addEventListener('change', () => {
        step.script = selectedRecord(scriptSelect, catalogs.scripts);
      });
      card.appendChild(el('label', {}, ['Script', scriptSelect]));
    } else {
      const ragSelect = selectFor(catalogs.ragProfiles, 'Choose RAG profile');
      ragSelect.value = step.rag_profile?.key || '';
      ragSelect.addEventListener('change', () => {
        step.rag_profile = selectedRecord(ragSelect, catalogs.ragProfiles);
      });
      card.appendChild(el('label', {}, ['RAG profile', ragSelect]));
      card.appendChild(renderInstructionPicker(app, step, catalogs.instructions));
    }

    card.appendChild(renderArgsEditor(step));

    const controls = el('div');
    controls.style.display = 'flex';
    controls.style.gap = '0.5rem';
    controls.append(
      button('↑', () => {
        if (index === 0) return;
        [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]];
        redraw();
      }),
      button('↓', () => {
        if (index === steps.length - 1) return;
        [steps[index + 1], steps[index]] = [steps[index], steps[index + 1]];
        redraw();
      }),
      button('Delete Step', () => {
        steps.splice(index, 1);
        redraw();
      })
    );
    card.appendChild(controls);
    stepsBox.appendChild(card);
  });
}

async function renderCreatePlan({ app, container }) {
  clear(container);

  const root = vaultRoot(app);
  const controlSnapshot = ascSnapshot('control', root);
  const registrySnapshot = ascSnapshot('registry', root);

  const catalogs = {
    engines: sortByLabel(snapshotList(registrySnapshot, 'engines')),
    models: sortByLabel(snapshotList(registrySnapshot, 'models')),
    scripts: sortByLabel(snapshotList(registrySnapshot, 'local_scripts')),
    ragProfiles: sortByLabel(snapshotList(registrySnapshot, 'rag_profiles')),
    instructions: sortByLabel(await feederListInstructions(app)),
  };

  let availablePlans = await feederListPlans(controlSnapshot);
  let loadedPlan = null;
  let newStepKind = 'llm';
  const steps = [];

  container.appendChild(button('Refresh', () => renderCreatePlan({ app, container })));
  container.appendChild(el('h2', { text: 'Define Plan' }));
  container.appendChild(el('p', { text: 'Plans are loaded from the control snapshot. Task, role, and context instruction components are synchronized separately before the plan is uploaded.' }));

  const existingSelect = el('select');
  existingSelect.style.width = '100%';
  const currentPlan = el('code', { text: 'new plan' });
  const label = el('input', { type: 'text', placeholder: 'Plan label' });
  label.style.width = '100%';
  const description = el('textarea', { placeholder: 'Optional description' });
  description.style.width = '100%';
  description.style.minHeight = '5rem';
  const stepsBox = el('div');

  function refreshPlanSelector(selectedSlug = '') {
    existingSelect.innerHTML = '';
    existingSelect.appendChild(el('option', {
      value: '',
      text: availablePlans.length ? 'Choose pipeline plan' : 'No pipeline plans found',
    }));
    for (const plan of availablePlans) {
      const slug = planSlug(plan);
      existingSelect.appendChild(el('option', { value: slug, text: optionText(plan) }));
    }
    existingSelect.value = selectedSlug;
  }

  function redrawSteps() {
    renderStepEditor({ app, stepsBox, steps, catalogs });
  }

  function clearScreen() {
    loadedPlan = null;
    currentPlan.textContent = 'new plan';
    existingSelect.value = '';
    label.value = '';
    description.value = '';
    steps.splice(0, steps.length);
    redrawSteps();
  }

  async function loadSelectedPlan() {
    if (!existingSelect.value) return;
    const plan = await feederLoadPlan(app, existingSelect.value);
    loadedPlan = plan;
    currentPlan.textContent = planSlug(plan);
    label.value = plan.label || '';
    description.value = plan.description || '';
    steps.splice(0, steps.length, ...planToScreenSteps(plan, catalogs));
    redrawSteps();
  }

  async function uploadCurrentPlan(forceSlug = null) {
    const instructionSets = prepareInstructionDependencies(app, steps);
    const record = buildPlanRecord({
      label: label.value,
      description: description.value,
      steps,
      force_slug: forceSlug,
    });
    await feederUploadPlan(app, record, instructionSets);

    const savedPlan = materializePlan(record);
    const savedSlug = planSlug(savedPlan);
    sessionPlanStore.set(savedSlug, savedPlan);

    availablePlans = await feederListPlans(controlSnapshot);
    loadedPlan = savedPlan;
    currentPlan.textContent = savedSlug;
    refreshPlanSelector(savedSlug);
    new Notice(`${forceSlug ? 'Updated' : 'Created'} plan: ${savedPlan.label}`);
  }

  const loadBtn = button('Load Plan', () => loadSelectedPlan().catch((error) => {
    new Notice(`Load plan failed: ${error.message}`, 10000);
    console.error(error);
  }));
  const newBtn = button('New Plan', clearScreen);
  const createBtn = button('Create Plan', () => uploadCurrentPlan(null).catch((error) => {
    new Notice(`Create plan failed: ${error.message}`, 10000);
    console.error(error);
  }));
  const updateBtn = button('Update Plan', () => {
    const slug = planSlug(loadedPlan);
    if (!slug) {
      new Notice('Load a plan before updating it.');
      return;
    }
    uploadCurrentPlan(slug).catch((error) => {
      new Notice(`Update plan failed: ${error.message}`, 10000);
      console.error(error);
    });
  });
  const addStepBtn = button('Add Step', () => {
    steps.push(emptyStep(newStepKind, steps.length + 1, catalogs));
    redrawSteps();
  });

  const planRow = el('div');
  planRow.style.display = 'flex';
  planRow.style.gap = '0.5rem';
  planRow.style.flexWrap = 'wrap';
  planRow.append(loadBtn, newBtn, el('span', {}, ['Current: ', currentPlan]));

  const addRow = el('div');
  addRow.style.display = 'flex';
  addRow.style.gap = '0.75rem';
  addRow.style.alignItems = 'center';
  addRow.append(
    addStepBtn,
    renderKindRadios({
      currentKind: newStepKind,
      name: 'new-step-kind',
      onChange: (kind) => { newStepKind = kind; },
    })
  );

  const actionRow = el('div');
  actionRow.style.display = 'flex';
  actionRow.style.gap = '0.5rem';
  actionRow.append(createBtn, updateBtn);

  refreshPlanSelector();
  container.append(
    el('label', {}, ['Existing pipeline plans', existingSelect]),
    planRow,
    el('label', {}, ['Plan label', label]),
    el('label', {}, ['Description', description]),
    el('p', { text: `${catalogs.instructions.length} instruction(s), ${llmEngines(catalogs.engines).length} LLM engine(s), ${catalogs.models.length} model(s), ${catalogs.scripts.length} script(s), ${catalogs.ragProfiles.length} RAG profile(s).` }),
    addRow,
    stepsBox,
    actionRow
  );

  if (catalogs.engines.length || catalogs.scripts.length || catalogs.ragProfiles.length) {
    addStepBtn.click();
  } else {
    redrawSteps();
  }
}

module.exports = { renderCreatePlan };
