const fs = require('fs');
const path = require('path');
const { makeSlug } = require('../lib/slug.js');
const { vaultRoot, writeJson } = require('../lib/vault-state.js');
const { controlWarnings } = require('../lib/control-loader.js');

function normalizeKind(value) {
  return String(value || '').trim().toLowerCase();
}

function compactControl(record) {
  if (!record) return null;
  return {
    slug: record.slug || record.record_identity || null,
    key: record.key || null,
    identity: record.identity || null,
    type: record.type || record.kind || null,
    kind: record.kind || record.type || null,
    label: record.label || record.slug || record.record_identity || record.key || null,
    description: record.description || '',
    path: record.path || null,
    abspath: record.abspath || null,
    exists: record.exists,
    size: record.size,
    mtime: record.mtime,
    repo_state: record.repo_state,
    git_status: record.git_status,
    git_commit: record.git_commit,
    short_commit: record.short_commit,
    has_prior_commit: record.has_prior_commit,
  };
}

function compactRegistryRecord(record) {
  if (!record) return null;
  return {
    key: record.key,
    slug: record.slug || null,
    kind: normalizeKind(record.kind || record.type),
    type: record.type || null,
    label: record.label || record.slug || record.key,
    description: record.description || '',
    module: record.module,
    callable: record.callable,
    step_fields: Array.isArray(record.step_fields) ? [...record.step_fields] : undefined,
  };
}

function parseArgsJson(text, stepNumber) {
  const trimmed = String(text || '').trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(`Step ${stepNumber}: args JSON must be an object.`);
  }
  return parsed;
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

function compactStepArgs(args) {
  const compact = {};
  for (const [key, value] of Object.entries(args || {})) {
    if (STEP_CONTRACT_ARG_KEYS.has(key)) continue;
    compact[key] = value;
  }
  return compact;
}

function normalizeStepKind(step) {
  const kind = normalizeKind(step?.kind || step?.step_kind || step?.type);
  if (kind === 'script' || kind === 'rag' || kind === 'llm') return kind;
  if (step?.script) return 'script';
  if (step?.rag_profile) return 'rag';
  return 'llm';
}

function hasExecutableTarget(step) {
  if (!step) return false;
  const kind = normalizeStepKind(step);
  if (kind === 'script') return Boolean(step.script);
  if (kind === 'rag') return Boolean(step.rag_profile);
  return Boolean(step.engine);
}

function planSlug(record) {
  return record?.record_identity || record?.slug || '';
}

function stepEntries(steps) {
  if (Array.isArray(steps)) {
    return steps.map((step, index) => [index + 1, step]);
  }

  if (!steps || typeof steps !== 'object') return [];

  return Object.entries(steps)
    .map(([key, step]) => [Number(key), step])
    .filter(([number, step]) => Number.isInteger(number) && number > 0 && step)
    .sort(([a], [b]) => a - b);
}

function buildPlanRecord({
  app,
  label,
  description,
  steps,
  registry_snapshot = null,
  control_snapshot = null,
  existing = null,
  force_slug = null,
}) {
  if (!label || !label.trim()) throw new Error('Plan label is required.');

  const cleanSteps = stepEntries(steps).filter(([, step]) => hasExecutableTarget(step));
  if (!cleanSteps.length) throw new Error('At least one executable step is required.');

  const root = vaultRoot(app);
  const recordIdentity = force_slug || planSlug(existing) || makeSlug('plan', label);
  const now = new Date().toISOString();
  const selectedControls = [];

  const planSteps = {};

  cleanSteps.forEach(([screenIndex, step]) => {
    const stepNumber = screenIndex;
    const kind = normalizeStepKind(step);
    const engine = compactRegistryRecord(step.engine);
    const script = compactRegistryRecord(step.script);
    const rag_profile = compactRegistryRecord(step.rag_profile);
    const model = compactRegistryRecord(step.model);
    const modelKey = String(model?.key || step.model || '').trim();

    if (kind === 'script' && !script) {
      throw new Error(`Step ${stepNumber}: choose a local script.`);
    }
    if (kind === 'rag' && !rag_profile) {
      throw new Error(`Step ${stepNumber}: choose a RAG profile.`);
    }
    if (kind === 'llm' && !engine) {
      throw new Error(`Step ${stepNumber}: choose an LLM provider/engine.`);
    }

    const instructions = (step.instructions || []).map(compactControl).filter(Boolean);
    for (const ins of instructions) selectedControls.push(ins);

    const args = compactStepArgs(parseArgsJson(step.argsJson, stepNumber));
    const instructionSlugs = instructions.map((ins) => ins.slug).filter(Boolean);
    const out = {
      index: stepNumber,
      kind,
      label: step.label || `Step ${stepNumber}`,
    };

    if (instructionSlugs.length) {
      out.instruction_slugs = instructionSlugs;
    }

    if (Object.keys(args).length) {
      out.args = args;
    }

    if (engine?.key) {
      out.engine = engine.key;
    }

    if (kind === 'llm') {
      if (!modelKey) throw new Error(`Step ${stepNumber}: choose a model.`);
      out.model = modelKey;
    }

    if (script?.key) {
      out.script = script.key;
    }

    if (rag_profile?.key) {
      out.rag_profile = rag_profile.key;
    }

    planSteps[String(stepNumber)] = out;
  });

  const warnings = controlWarnings(selectedControls);
  const cleanDescription = (description || '').trim();

  return {
    record_type: 'plan',
    record_identity: recordIdentity,
    record_content: cleanDescription,

    version: Number(existing?.version || 0) + 1,
    label: label.trim(),

    // UI/local compatibility only. Pipeline upload contract uses record_identity.
    slug: recordIdentity,

    description: cleanDescription,
    created: existing?.created || now,
    modified: now,
    vault: {
      name: path.basename(root),
      root,
      storage: 'vault-local',
    },
    registry_snapshot,
    control_snapshot,
    step_count: Object.keys(planSteps).length,
    preflight: {
      clean: warnings.length === 0,
      warnings,
    },
    steps: planSteps,
  };
}

function localAutoscribeDir(app) {
  return path.join(vaultRoot(app), '.autoscribe');
}

function planDatabaseFile(app) {
  return path.join(localAutoscribeDir(app), 'plans.json');
}

function readPlanDatabase(app) {
  const file = planDatabaseFile(app);
  if (!fs.existsSync(file)) return { schema_version: 1, plans: {} };
  const value = readJsonFile(file);
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${file}: plan database must be an object.`);
  }
  if (!value.plans || typeof value.plans !== 'object' || Array.isArray(value.plans)) {
    value.plans = {};
  }
  value.schema_version = Number(value.schema_version || 1);
  return value;
}

function savePlanDatabase(app, database) {
  writeJson(planDatabaseFile(app), database);
  return planDatabaseFile(app);
}

function savePlanRecord(app, record) {
  const slug = planSlug(record);
  if (!slug) throw new Error('Plan record missing record_identity.');
  const database = readPlanDatabase(app);
  database.plans[slug] = { ...record, record_identity: slug, slug };
  savePlanDatabase(app, database);
  return planDatabaseFile(app);
}

function readJsonFile(file) {
  const text = fs.readFileSync(file, 'utf8');
  return JSON.parse(text);
}

function isPlanRecord(record) {
  return record && record.record_type === 'plan' && Boolean(record.record_identity || record.slug);
}

function listPlanRecords(app) {
  const database = readPlanDatabase(app);
  return Object.entries(database.plans)
    .map(([slug, record]) => ({ ...record, record_identity: slug, slug }))
    .filter(isPlanRecord)
    .sort((a, b) => {
      const am = String(a.modified || a.created || '');
      const bm = String(b.modified || b.created || '');
      return bm.localeCompare(am) || String(a.label || a.slug).localeCompare(String(b.label || b.slug));
    });
}

function loadPlanRecord(app, slug) {
  const database = readPlanDatabase(app);
  const record = database.plans[String(slug || '').trim()];
  if (!record) throw new Error(`Plan not found: ${slug}`);
  return { ...record, record_identity: slug, slug };
}

function deletePlanRecord(app, slug) {
  const database = readPlanDatabase(app);
  if (!database.plans[slug]) throw new Error(`Plan not found: ${slug}`);
  delete database.plans[slug];
  savePlanDatabase(app, database);
  return planDatabaseFile(app);
}

module.exports = {
  buildPlanRecord,
  planDatabaseFile,
  readPlanDatabase,
  savePlanDatabase,
  savePlanRecord,
  listPlanRecords,
  loadPlanRecord,
  deletePlanRecord,
};
