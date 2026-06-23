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

  const cleanSteps = (steps || []).filter(hasExecutableTarget);
  if (!cleanSteps.length) throw new Error('At least one executable step is required.');

  const root = vaultRoot(app);
  const recordIdentity = force_slug || planSlug(existing) || makeSlug('plan', label);
  const now = new Date().toISOString();
  const selectedControls = [];

  const planSteps = cleanSteps.map((step, index) => {
    const stepNumber = index + 1;
    const kind = normalizeStepKind(step);
    const engine = compactRegistryRecord(step.engine);
    const script = compactRegistryRecord(step.script);
    const rag_profile = compactRegistryRecord(step.rag_profile);
    const model = String(step.model || '').trim();

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
      instruction_slugs: instructionSlugs,
      args,
    };

    if (engine?.key) {
      out.engine = engine.key;
    }

    if (kind === 'llm' && model) {
      out.model = model;
    }

    if (script?.key) {
      out.script = script.key;
    }

    if (rag_profile?.key) {
      out.rag_profile = rag_profile.key;
    }

    return out;
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
    pending_upload: true,
    uploaded_at: existing?.uploaded_at || null,
    vault: {
      name: path.basename(root),
      root,
      storage: 'vault-local',
    },
    registry_snapshot,
    control_snapshot,
    step_count: planSteps.length,
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

function workflowDir(app, name) {
  return path.join(localAutoscribeDir(app), 'workflow', name);
}

function planDir(app) {
  return workflowDir(app, 'plans');
}

function planFileFor(app, slug) {
  return path.join(planDir(app), `${slug}.json`);
}

function savePlanRecord(app, record) {
  const slug = planSlug(record);
  if (!slug) throw new Error('Plan record missing record_identity.');
  const file = planFileFor(app, slug);
  writeJson(file, record);
  return file;
}

function readJsonFile(file) {
  const text = fs.readFileSync(file, 'utf8');
  return JSON.parse(text);
}

function isPlanRecord(record) {
  return record && record.record_type === 'plan' && Boolean(record.record_identity);
}

function listPlanRecords(app) {
  const dir = planDir(app);
  let entries = [];
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return []; }

  const records = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith('.json')) continue;

    const file = path.join(dir, entry.name);
    try {
      const record = readJsonFile(file);
      if (!isPlanRecord(record)) continue;

      const stat = fs.statSync(file);
      records.push({
        ...record,
        slug: record.record_identity,
        file,
        file_mtime: stat.mtime.toISOString(),
      });
    } catch (err) {
      const fallbackSlug = path.basename(entry.name, '.json');
      records.push({
        record_type: 'plan',
        record_identity: fallbackSlug,
        slug: fallbackSlug,
        label: fallbackSlug,
        file,
        read_error: err.message,
      });
    }
  }

  records.sort((a, b) => {
    const am = String(a.modified || a.file_mtime || a.created || '');
    const bm = String(b.modified || b.file_mtime || b.created || '');
    const cmp = bm.localeCompare(am);
    if (cmp) return cmp;
    return String(a.label || a.record_identity || a.slug).localeCompare(
      String(b.label || b.record_identity || b.slug)
    );
  });

  return records;
}

function loadPlanRecord(app, slug) {
  const found = listPlanRecords(app).find((record) => planSlug(record) === slug);
  if (!found) throw new Error(`Plan not found: ${slug}`);
  if (found.read_error) throw new Error(`Could not read ${found.file}: ${found.read_error}`);
  return found;
}

function listPendingPlanRecords(app) {
  return listPlanRecords(app).filter((record) => record.pending_upload === true);
}

function markPlanRecordUploaded(app, slug, uploadedAt = new Date().toISOString()) {
  const record = loadPlanRecord(app, slug);
  record.pending_upload = false;
  record.uploaded_at = uploadedAt;
  savePlanRecord(app, record);
  return record;
}

function deletePlanRecord(app, slug) {
  const record = loadPlanRecord(app, slug);
  fs.unlinkSync(record.file || planFileFor(app, slug));
  return record.file || planFileFor(app, slug);
}

module.exports = {
  buildPlanRecord,
  savePlanRecord,
  listPlanRecords,
  loadPlanRecord,
  listPendingPlanRecords,
  markPlanRecordUploaded,
  deletePlanRecord,
};