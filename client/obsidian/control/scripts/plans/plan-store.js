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
    slug: record.slug || null,
    key: record.key || null,
    identity: record.identity || null,
    type: record.type || record.kind || null,
    kind: record.kind || record.type || null,
    label: record.label || record.slug || record.key || null,
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
  const slug = force_slug || existing?.slug || makeSlug('plan', label);
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

    const args = parseArgsJson(step.argsJson, stepNumber);
    const out = {
      index: stepNumber,
      kind,
      label: step.label || `Step ${stepNumber}`,
      instructions,
      instruction_slugs: instructions.map((ins) => ins.slug).filter(Boolean),
      args,
    };

    if (engine) {
      out.engine = engine;
      if (!out.args.engine && engine.key) out.args.engine = engine.key;
    }

    if (kind === 'llm' && model) {
      out.model = model;
      if (!out.args.model) out.args.model = model;
    }

    if (script) {
      out.script = script;
      if (!out.args.script && script.key) out.args.script = script.key;
    }

    if (rag_profile) {
      out.rag_profile = rag_profile;
      if (!out.args.rag_profile && rag_profile.key) out.args.rag_profile = rag_profile.key;
    }

    return out;
  });

  const warnings = controlWarnings(selectedControls);
  return {
    type: 'plan',
    version: Number(existing?.version || 0) + 1,
    label: label.trim(),
    slug,
    description: (description || '').trim(),
    created: existing?.created || new Date().toISOString(),
    modified: new Date().toISOString(),
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
  const file = planFileFor(app, record.slug);
  writeJson(file, record);
  return file;
}

function readJsonFile(file) {
  const text = fs.readFileSync(file, 'utf8');
  return JSON.parse(text);
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
      if (!record || record.type !== 'plan' || !record.slug) continue;
      const stat = fs.statSync(file);
      records.push({ ...record, file, file_mtime: stat.mtime.toISOString() });
    } catch (err) {
      records.push({
        type: 'plan',
        slug: path.basename(entry.name, '.json'),
        label: path.basename(entry.name, '.json'),
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
    return String(a.label || a.slug).localeCompare(String(b.label || b.slug));
  });
  return records;
}

function loadPlanRecord(app, slug) {
  const found = listPlanRecords(app).find((record) => record.slug === slug);
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
