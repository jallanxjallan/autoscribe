const fs = require('fs');
const path = require('path');

const { el, clear, button } = require('../lib/dom.js');
const { vaultRoot } = require('../lib/vault-state.js');
const { loadRegistrySnapshot, snapshotList } = require('../lib/control-loader.js');

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

const GLOBAL_INSTRUCTIONS_DIR = '/home/jeremy/Library/instructions';
const GLOBAL_PLANS_DIR = '/home/jeremy/Library/instructions';
const ENGINES_DIR = '/home/jeremy/AutoScribe/extensions/engines';
const LOCAL_SCRIPTS_DIR = '/home/jeremy/AutoScribe/extensions/scripts';

function fileExists(file) {
  try {
    return fs.existsSync(file);
  } catch {
    return false;
  }
}

function safeStat(file) {
  try {
    return fs.statSync(file);
  } catch {
    return null;
  }
}

function walkFiles(root, extensions) {
  const base = String(root || '');
  const found = [];
  const stat = safeStat(base);
  if (!stat || !stat.isDirectory()) return found;

  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!entry.isFile()) continue;
      const ext = path.extname(entry.name).toLowerCase();
      if (extensions.has(ext)) found.push(full);
    }
  }

  walk(base);
  return found;
}

function relativeSlug(root, file) {
  const rel = path.relative(root, file);
  const parsed = path.parse(rel);
  const withoutExt = path.join(parsed.dir, parsed.name);
  return withoutExt.split(path.sep).filter(Boolean).join('/');
}

function labelFromSlug(slug) {
  const leaf = String(slug || '').split('/').filter(Boolean).pop() || String(slug || '');
  return leaf
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    || String(slug || '');
}

function recordModified(file) {
  const stat = safeStat(file);
  return stat ? stat.mtime.toISOString() : '';
}

function listInstructionFolder(root, source) {
  return walkFiles(root, new Set(['.md', '.txt']))
    .map((file) => {
      const slug = relativeSlug(root, file);
      return {
        source,
        key: slug,
        slug,
        label: labelFromSlug(slug),
        path: file,
        kind: 'instruction',
        modified: recordModified(file),
      };
    });
}

function parseFrontmatter(text) {
  const match = String(text || '').match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return {};

  const data = {};
  for (const line of match[1].split(/\r?\n/)) {
    const clean = line.trim();
    if (!clean || clean.startsWith('#')) continue;

    const sep = clean.indexOf(':');
    if (sep < 0) continue;

    const key = clean.slice(0, sep).trim();
    let value = clean.slice(sep + 1).trim();
    value = value.replace(/^['"]|['"]$/g, '');
    data[key] = value;
  }

  return data;
}

function shouldSkipVaultMarkdown(root, file) {
  const rel = path.relative(root, file);
  const parts = rel.split(path.sep);
  if (parts.some((part) => part.startsWith('.'))) return true;
  if (parts[0] === '_control') return true;
  if (parts[0] === 'node_modules') return true;
  return false;
}

function listVaultSlugInstructions(root) {
  return walkFiles(root, new Set(['.md']))
    .filter((file) => !shouldSkipVaultMarkdown(root, file))
    .map((file) => {
      let frontmatter = {};
      let read_error = '';

      try {
        frontmatter = parseFrontmatter(fs.readFileSync(file, 'utf8'));
      } catch (err) {
        read_error = err.message;
      }

      const slug = String(frontmatter.slug || '').trim();
      if (!slug.startsWith('ins.')) return null;

      return {
        source: 'vault',
        key: slug,
        slug,
        label: frontmatter.title || labelFromSlug(slug),
        path: file,
        kind: 'instruction',
        modified: recordModified(file),
        read_error,
      };
    })
    .filter(Boolean);
}

function listPlanFolder(root, source) {
  return walkFiles(root, new Set(['.json']))
    .map((file) => {
      const slug = relativeSlug(root, file);
      let label = labelFromSlug(slug);
      let step_count = null;
      let read_error = '';

      try {
        const data = JSON.parse(fs.readFileSync(file, 'utf8'));
        label = data.label || data.title || label;
        if (Array.isArray(data.steps)) step_count = data.steps.length;
        else if (data.steps && typeof data.steps === 'object') step_count = Object.keys(data.steps).length;
      } catch (err) {
        read_error = err.message;
      }

      return {
        source,
        key: `${source}:${slug}`,
        slug,
        record_identity: slug,
        label,
        file,
        step_count,
        modified: recordModified(file),
        read_error,
      };
    });
}

function engineKindFromName(name) {
  const clean = String(name || '').trim().toLowerCase();
  if (clean === 'script' || clean === 'scripts' || clean.includes('script')) return 'script';
  if (clean === 'rag' || clean.includes('rag')) return 'rag';
  return 'llm';
}

function listEngineFolder(root) {
  const stat = safeStat(root);
  if (!stat || !stat.isDirectory()) return [];

  const records = [];

  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (entry.name.startsWith('_') || entry.name.startsWith('.')) continue;

    if (entry.isFile() && path.extname(entry.name) === '.py') {
      const stem = path.basename(entry.name, '.py');
      if (stem === '__init__') continue;
      records.push({
        source: 'local',
        key: stem,
        slug: stem,
        label: labelFromSlug(stem),
        kind: engineKindFromName(stem),
        path: path.join(root, entry.name),
        modified: recordModified(path.join(root, entry.name)),
      });
    }

    if (entry.isDirectory()) {
      const initFile = path.join(root, entry.name, '__init__.py');
      if (!fileExists(initFile)) continue;
      records.push({
        source: 'local',
        key: entry.name,
        slug: entry.name,
        label: labelFromSlug(entry.name),
        kind: engineKindFromName(entry.name),
        path: path.join(root, entry.name),
        modified: recordModified(initFile),
      });
    }
  }

  return records;
}

function listScriptFolder(root) {
  return walkFiles(root, new Set(['.py']))
    .filter((file) => !path.basename(file).startsWith('_'))
    .map((file) => {
      const slug = relativeSlug(root, file);
      const key = slug.split('/').join('.');
      return {
        source: 'local',
        key,
        slug: key,
        label: labelFromSlug(slug),
        kind: 'script',
        path: file,
        modified: recordModified(file),
      };
    });
}

function loadPlanFromFile(record) {
  const data = JSON.parse(fs.readFileSync(record.file, 'utf8'));
  return {
    ...data,
    file: record.file,
    slug: data.slug || data.record_identity || record.slug,
    record_identity: data.record_identity || data.slug || record.slug,
    label: data.label || record.label,
  };
}

function normalizeKind(value) {
  return String(value || '').trim().toLowerCase();
}

function planSlug(record) {
  return record?.record_identity || record?.slug || '';
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
  const id = record.record_identity || record.slug || record.key || '';
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
  const slug = planSlug(record);
  return `${record.label || slug} — ${slug}${count}${changed ? ` (${changed})` : ''}${bad}`;
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

  if (typeof saved === 'string') {
    return liveRecords.find((record) => (
      record[valueField] || record.slug || record.key
    ) === saved) || { [valueField]: saved, key: saved, slug: saved };
  }

  const savedId = saved[valueField] || saved.slug || saved.key;
  return liveRecords.find((record) => (record[valueField] || record.slug || record.key) === savedId) || saved;
}

const STEP_CONTRACT_ARG_KEYS = new Set([
  'index',
  'kind',
  'label',
  'instructions',
  'instruction_slugs',
  'engine',
  'script',
  'rag_profile',
  'model',
]);

function argsForEditor(args) {
  const compact = {};
  for (const [key, value] of Object.entries(args || {})) {
    if (STEP_CONTRACT_ARG_KEYS.has(key)) continue;
    compact[key] = value;
  }
  return compact;
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

function modelEngineKey(model) {
  return String(model?.engine || model?.engine_key || model?.provider || model?.provider_key || '').trim();
}

function modelsForEngine(models, engine) {
  if (!engine) return [];
  const engineKey = String(engine.key || '').trim();
  return models.filter((model) => {
    const owner = modelEngineKey(model);
    return !owner || owner === engineKey;
  });
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
    index,
    kind,
    label: `Step ${index}`,
    engine: null,
    model: null,
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
    step.model = null;
  } else if (kind === 'rag') {
    step.engine = findRagEngine(engines);
    step.script = null;
    step.model = null;
  } else {
    step.engine = llmEngines(engines).find((engine) => engine.key === step.engine?.key) || llmEngines(engines)[0] || step.engine || null;
    step.script = null;
    step.rag_profile = null;
  }
}

function ensurePlanUploadContract(record) {
  const plan = { ...record };
  const identity = plan.record_identity || plan.slug;
  if (!identity) throw new Error('Plan must have record_identity');
  plan.record_type = 'plan';
  plan.record_identity = identity;
  if (typeof plan.record_content !== 'string') {
    plan.record_content = typeof plan.description === 'string' ? plan.description : '';
  }
  return plan;
}

function planStepEntries(steps) {
  if (Array.isArray(steps)) {
    return steps.map((step, index) => [index + 1, step]);
  }

  if (!steps || typeof steps !== 'object') return [];

  return Object.entries(steps)
    .map(([key, step]) => [Number(key), step])
    .filter(([number, step]) => Number.isInteger(number) && number > 0 && step)
    .sort(([a], [b]) => a - b);
}

function planToScreenSteps(plan, { engines, models, instructions, scripts, ragProfiles }) {
  return planStepEntries(plan.steps).map(([stepNumber, step]) => {
    const kind = inferStepKind(step);
    const screenStep = {
      index: Number(step.index || stepNumber),
      kind,
      label: step.label || `Step ${stepNumber}`,
      engine: hydrateControl(step.engine, engines, 'key'),
      script: hydrateControl(step.script, scripts, 'key'),
      rag_profile: hydrateControl(step.rag_profile, ragProfiles, 'key'),
      model: hydrateControl(step.model || step.args?.model, models, 'key'),
      argsJson: JSON.stringify(argsForEditor(step.args || {}), null, 2),
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

function renderProviderPicker({ step, engines, redraw }) {
  const providers = llmEngines(engines);
  const engineSelect = selectFor(providers, providers.length ? 'Choose provider/engine' : 'No LLM engines in registry snapshot', 'key');
  engineSelect.value = step.engine?.key || '';
  engineSelect.addEventListener('change', () => {
    step.engine = selectedRecord(engineSelect, providers, 'key');
    step.model = null;
    redraw();
  });
  return el('label', {}, ['Provider / engine', engineSelect]);
}

function renderModelPicker({ step, models }) {
  const choices = modelsForEngine(models, step.engine);
  const modelSelect = selectFor(
    choices,
    choices.length ? 'Choose model' : 'No models registered for this engine',
    'key'
  );
  modelSelect.value = step.model?.key || '';
  modelSelect.addEventListener('change', () => {
    step.model = selectedRecord(modelSelect, choices, 'key');
  });
  return el('label', {}, ['Model', modelSelect]);
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
  const ragSelect = selectFor(ragProfiles, ragProfiles.length ? 'Choose RAG profile' : 'No RAG profiles found', 'key');
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

function renderStepSpecificControls({ step, engines, models, scripts, instructions, ragProfiles, redraw }) {
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

  wrapper.appendChild(renderProviderPicker({ step, engines, redraw }));
  wrapper.appendChild(renderModelPicker({ step, models }));
  wrapper.appendChild(renderInstructionPicker({ step, instructions, redraw }));
  wrapper.appendChild(renderArgsEditor(step, 'Optional LLM args JSON'));
  return wrapper;
}

function renderStepEditor({ stepsBox, engines, models, scripts, instructions, ragProfiles, steps }) {
  function redraw() {
    renderStepEditor({ stepsBox, engines, models, scripts, instructions, ragProfiles, steps });
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
    card.appendChild(renderStepSpecificControls({ step, engines, models, scripts, instructions, ragProfiles, redraw }));
    card.appendChild(controls);
    stepsBox.appendChild(card);
  });
}

async function renderCreatePlan({ app, container }) {
  clear(container);

  const refreshBtn = button('Refresh', async () => {
    try {
      await renderCreatePlan({ app, container });
    } catch (error) {
      new Notice(`Define Plan refresh failed: ${error.message}`, 10000);
      console.error(error);
    }
  });
  container.appendChild(refreshBtn);
  const root = vaultRoot(app);
  const vaultControlRoot = path.join(root, '.autoscribe');
  const vaultPlansDir = path.join(vaultControlRoot, 'plans');

  const registryResult = loadRegistrySnapshot();
  if (registryResult.error) {
    throw new Error(`Could not load AutoScribe registry snapshot: ${registryResult.error}${registryResult.stderr ? `; ${registryResult.stderr}` : ''}`);
  }
  const registrySnapshot = registryResult.data;
  const engines = sortByLabel(snapshotList(registrySnapshot, 'engines'));
  const models = sortByLabel(snapshotList(registrySnapshot, 'models'));
  const scripts = sortByLabel(snapshotList(registrySnapshot, 'local_scripts'));
  const ragProfiles = sortByLabel(snapshotList(registrySnapshot, 'rag_profiles'));
  const instructions = sortByLabel([
    ...listInstructionFolder(GLOBAL_INSTRUCTIONS_DIR, 'global'),
    ...listVaultSlugInstructions(root),
  ]);
  const globalPlans = sortByLabel([
    ...listPlanFolder(GLOBAL_PLANS_DIR, 'global'),
    ...listPlanFolder(vaultPlansDir, 'vault'),
  ]);

  const steps = [];
  let loadedPlan = null;
  let newStepKind = 'llm';
  let availablePlans = [];

  container.appendChild(el('h2', { text: 'Define Plan' }));
  container.appendChild(el('p', { text: 'A plan is a reusable ordered set of processing steps. Pick a step type first; the screen then shows only the relevant provider, model, script, RAG, instruction, and args fields.' }));
  container.appendChild(el('p', {}, ['Helper path: ', el('code', { text: `${root}/_control/scripts/plans/render-create-plan.js` })]));

  const existingPlansBox = el('div');
  const existingSelect = el('select');
  existingSelect.style.width = '100%';
  const currentPlan = el('code', { text: 'new unsaved plan' });

  function refreshExistingPlans(selectedSlug = '') {
    const savedPlans = listPlanRecords(app).map((plan) => ({
      ...plan,
      source: plan.source || 'saved',
      key: `saved:${plan.slug}`,
    }));
    availablePlans = sortByLabel([...savedPlans, ...globalPlans]);
    existingSelect.innerHTML = '';
    existingSelect.appendChild(el('option', { value: '', text: availablePlans.length ? 'Choose existing/local plan' : 'No saved or local plans found' }));
    for (const plan of availablePlans) {
      existingSelect.appendChild(el('option', { value: plan.key || plan.slug, text: planOptionText(plan) }));
    }
    if (selectedSlug) {
      existingSelect.value = selectedSlug.includes(':') ? selectedSlug : `saved:${selectedSlug}`;
      if (!existingSelect.value) existingSelect.value = selectedSlug;
    }
  }

  const label = el('input', { type: 'text', placeholder: 'Plan label, e.g. Fact Check' });
  label.style.width = '100%';
  const description = el('textarea', { placeholder: 'Optional description' });
  description.style.width = '100%';
  description.style.minHeight = '5rem';

  const status = el('p', {
    text: `${instructions.length} instruction(s), ${llmEngines(engines).length} LLM engine(s), ${models.length} model(s), ${scripts.length} script(s), ${ragProfiles.length} RAG profile(s), ${globalPlans.length} local plan(s) found.`,
  });
  const rootsText = el('p', {
    text: `Registry source: asc registry snapshot; global instructions=${GLOBAL_INSTRUCTIONS_DIR}; active vault instructions=Markdown files with slug ins.*; plans=${GLOBAL_PLANS_DIR}; vault plans=${vaultPlansDir}`,
  });
  const stepsBox = el('div');
  const savedPath = el('code', { text: '' });

  function redrawSteps() {
    renderStepEditor({ stepsBox, engines, models, scripts, instructions, ragProfiles, steps });
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
    const selectedKey = existingSelect.value;
    if (!selectedKey) return;
    const selected = availablePlans.find((plan) => (plan.key || plan.slug) === selectedKey);
    if (!selected) return;
    try {
      const plan = selected.source === 'saved'
        ? loadPlanRecord(app, selected.slug)
        : loadPlanFromFile(selected);
      loadedPlan = plan;
      currentPlan.textContent = `${planSlug(plan)} (${plan.file || 'saved plan'})`;
      savedPath.textContent = plan.file || '';
      label.value = plan.label || '';
      description.value = plan.description || '';
      steps.splice(0, steps.length, ...planToScreenSteps(plan, { engines, models, instructions, scripts, ragProfiles }));
      redrawSteps();
      new Notice(`Loaded plan: ${plan.label || plan.slug}`);
    } catch (err) {
      new Notice(`Load plan failed: ${err.message}`);
      console.error(err);
    }
  }

  function snapshotPayload(existing = null, forceSlug = null) {
    const record = buildPlanRecord({
      app,
      label: label.value,
      description: description.value,
      steps,
      existing,
      force_slug: forceSlug,
      registry_snapshot: registrySnapshot,
      control_snapshot: {
        source: 'local-folders',
        global_instructions_dir: GLOBAL_INSTRUCTIONS_DIR,
        global_plans_dir: GLOBAL_PLANS_DIR,
        vault_instruction_rule: 'active vault Markdown files with slug ins.*',
        vault_plans_dir: vaultPlansDir,
      },
    });
    console.log(JSON.stringify(record, null, 2));
    return ensurePlanUploadContract(record);
  }

  

  function saveRecord(record) {
    const file = savePlanRecord(app, record);
    savedPath.textContent = file;
    loadedPlan = { ...record, file };
    currentPlan.textContent = `${planSlug(record)} (${file})`;
    refreshExistingPlans(planSlug(record));
    const warn = record.preflight.warnings.length ? ` (${record.preflight.warnings.join('; ')})` : '';
    new Notice(`Saved plan: ${record.label}${warn}`);
  }

  const loadBtn = button('Modify Selected Plan', loadSelectedPlan);
  const newBtn = button('New Blank Plan', clearScreen);
  const deleteBtn = button('Delete Selected Plan', () => {
    const selectedKey = existingSelect.value;
    const selected = availablePlans.find((plan) => (plan.key || plan.slug) === selectedKey);
    const slug = selected?.slug || planSlug(loadedPlan);
    if (!slug || (selected && selected.source !== 'saved')) {
      new Notice('Choose a saved plan to delete. Local folder plans are read-only here.');
      return;
    }
    if (!confirm(`Delete plan ${slug}?`)) return;
    try {
      const file = deletePlanRecord(app, slug);
      if (planSlug(loadedPlan) === slug) clearScreen();
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
    if (!planSlug(loadedPlan)) {
      new Notice('Load a plan first, or use Save Screen as New Plan.');
      return;
    }
    try {
      saveRecord(snapshotPayload(loadedPlan, planSlug(loadedPlan)));
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

  if (!engines.length) {
    new Notice('Define Plan: no engines found in the registry snapshot.');
  }
  if (!instructions.length) {
    new Notice(`Define Plan: no instructions found in ${GLOBAL_INSTRUCTIONS_DIR} or active vault Markdown files with slug ins.*`);
  }
  if (engines.length || scripts.length || ragProfiles.length) addStep.click();
  else redrawSteps();
}

module.exports = { renderCreatePlan };
