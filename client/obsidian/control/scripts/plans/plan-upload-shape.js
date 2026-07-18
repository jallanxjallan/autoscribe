'use strict';

const INSTRUCTION_LABELS = Object.freeze([
  'role',
  'context',
  'instructions',
]);

function scalarId(value, ...fields) {
  if (typeof value === 'string') return value.trim();

  if (value && typeof value === 'object') {
    for (const field of fields) {
      const candidate = value[field];
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim();
      }
    }
  }

  return '';
}

function parseArgsJson(value, stepNumber) {
  const text = String(value || '').trim();
  if (!text) return {};

  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`Step ${stepNumber} args are not valid JSON: ${error.message}`);
  }

  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error(`Step ${stepNumber} args must decode to an object`);
  }

  return parsed;
}

function instructionSlug(value) {
  return scalarId(value, 'slug', 'record_identity', 'key');
}

function normalizeInstructionSlugs(step, stepNumber) {
  const source = step.instruction_slugs || step.instructions || {};
  const result = {};

  /*
   * Temporary fixed engine contract:
   *   role -> context -> instructions
   *
   * The object labels, rather than JavaScript property order, are authoritative.
   * Engines currently stack populated values in INSTRUCTION_LABELS order.
   */
  for (const label of INSTRUCTION_LABELS) {
    const slug = instructionSlug(source[label]);
    if (slug) result[label] = slug;
  }

  /*
   * Fail loudly if the old generic list reaches the uploader. It cannot be
   * converted safely because its members have no semantic labels.
   */
  if (Array.isArray(source) && source.length) {
    throw new Error(
      `Step ${stepNumber} still contains an unlabeled instruction list; ` +
      'select Role, Context, and Instructions explicitly'
    );
  }

  return result;
}

function normalizeStep(step, ordinal) {
  if (!step || typeof step !== 'object' || Array.isArray(step)) {
    throw new Error(`Step ${ordinal} must be an object`);
  }

  const kind = scalarId(step.kind, 'key', 'slug').toLowerCase();
  if (!['llm', 'script', 'rag'].includes(kind)) {
    throw new Error(
      `Step ${ordinal} kind must be llm, script, or rag; got ${kind || 'empty'}`
    );
  }

  const engine = scalarId(step.engine, 'key', 'slug');
  if (!engine) throw new Error(`Step ${ordinal} must select an engine`);

  const definition = {
    kind,
    label: String(step.label || `Step ${ordinal}`).trim(),
    engine,
    instruction_slugs: normalizeInstructionSlugs(step, ordinal),
  };

  if (kind === 'llm') {
    const model = scalarId(step.model, 'key', 'slug');
    if (!model) throw new Error(`Step ${ordinal} must select a model`);
    definition.model = model;
  } else if (kind === 'script') {
    const script = scalarId(step.script, 'key', 'slug');
    if (!script) throw new Error(`Step ${ordinal} must select a script`);
    definition.script = script;
  } else {
    const ragProfile = scalarId(step.rag_profile, 'key', 'slug');
    if (!ragProfile) throw new Error(`Step ${ordinal} must select a RAG profile`);
    definition.rag_profile = ragProfile;
  }

  const args = parseArgsJson(step.argsJson, ordinal);
  if (Object.keys(args).length) definition.args = args;

  return definition;
}

function indexedSteps(screenSteps) {
  if (!Array.isArray(screenSteps)) {
    throw new Error('Plan screen steps must be an array');
  }
  if (!screenSteps.length) {
    throw new Error('Plan must contain at least one step');
  }

  return Object.fromEntries(
    screenSteps.map((step, index) => {
      const ordinal = index + 1;
      return [String(ordinal), normalizeStep(step, ordinal)];
    })
  );
}

function buildPlanUploadRecord({
  baseRecord,
  label,
  description,
  steps,
}) {
  if (!baseRecord || typeof baseRecord !== 'object' || Array.isArray(baseRecord)) {
    throw new Error('buildPlanRecord() must return an object');
  }

  const recordIdentity = scalarId(
    baseRecord.record_identity || baseRecord.slug,
    'record_identity',
    'slug'
  );
  if (!recordIdentity) throw new Error('Plan must have record_identity');

  /*
   * This is the complete public upload envelope.
   * No Plan/Redis implementation fields are copied into it.
   */
  return {
    record_type: 'plan',
    record_identity: recordIdentity,
    record_content: {
      label: String(label || baseRecord.label || '').trim(),
      description: String(description || baseRecord.description || '').trim(),
      steps: indexedSteps(steps),
    },
  };
}

module.exports = {
  INSTRUCTION_LABELS,
  buildPlanUploadRecord,
};
