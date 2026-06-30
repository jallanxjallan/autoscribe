'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail, info } = require('./command');
const { assertVaultRoot } = require('./selection');
const { sha256 } = require('./records');

const { getGitRoot } = require('../../lib/git');
const { slugPrefix } = require('../../lib/slug');

const SCRIPT = 'upload-plans';

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--force]

Behavior:
  Normal mode uploads local plan JSON records marked pending_upload=true.
  Plan records are read from .autoscribe/workflow/plans in the active vault.

  Force mode uploads every local plan JSON record for the active vault,
  regardless of pending_upload state.

  Human messages are written to stderr. Valid plan records are emitted as
  NDJSON on stdout. The emitted plan record is intentionally shallow: it keeps
  instruction_slugs as references and does not embed instruction content.

Options:
  -n, --dry-run              Show what would be uploaded; do not emit NDJSON or reset state.
  -f, --force                Upload all local plans for this vault.
  -h, --help                 Show this help.
`);
}

function parseArgs(argv, script) {
  const options = {
    dryRun: false,
    force: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === '--dry-run' || arg === '-n') {
      options.dryRun = true;
    } else if (arg === '--force' || arg === '-f') {
      options.force = true;
    } else if (arg === '--help' || arg === '-h') {
      usage(script);
      process.exit(0);
    } else {
      fail(script, `unknown argument: ${arg}`);
    }
  }

  return options;
}

function planJsonFiles(root) {
  const plansDir = path.join(path.resolve(root), '.autoscribe', 'workflow', 'plans');
  let planEntries = [];

  try {
    planEntries = fs.readdirSync(plansDir, { withFileTypes: true });
  } catch {
    return [];
  }

  return planEntries
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => path.join(plansDir, entry.name))
    .sort((a, b) => a.localeCompare(b));
}

function readPlanJson(file) {
  const text = fs.readFileSync(file, 'utf8');
  return JSON.parse(text);
}

function planBelongsToRoot(record, root, file) {
  const expectedRoot = path.resolve(root);
  const recordRoot = record?.vault?.root ? path.resolve(record.vault.root) : '';

  if (recordRoot && recordRoot === expectedRoot) {
    return true;
  }

  const recordVaultName = String(record?.vault?.name || '').trim().toLowerCase();
  const rootName = path.basename(expectedRoot).trim().toLowerCase();

  if (recordVaultName && recordVaultName === rootName) {
    return true;
  }

  const localPlansDir = path.join(expectedRoot, '.autoscribe', 'workflow', 'plans');
  return path.dirname(file) === localPlansDir;
}

function planRecordIdentity(record) {
  return typeof record?.record_identity === 'string'
    ? record.record_identity.trim()
    : '';
}

function isPlanUploadRecord(record) {
  return record && record.record_type === 'plan' && Boolean(planRecordIdentity(record));
}

function normalizeInstructionSlugs(value) {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => String(item || '').trim())
    .filter(Boolean);
}

function normalizeStep(rawStep, index) {
  const source = rawStep && typeof rawStep === 'object' ? rawStep : {};
  const number = Number(source.index || source.number || index);
  const args = source.args && typeof source.args === 'object' && !Array.isArray(source.args)
    ? source.args
    : {};

  return {
    index: Number.isInteger(number) && number > 0 ? number : index,
    kind: String(source.kind || ''),
    label: String(source.label || `Step ${index}`),
    engine: String(source.engine || ''),
    script: String(source.script || ''),
    rag_profile: String(source.rag_profile || source.ragProfile || ''),
    instruction_slugs: normalizeInstructionSlugs(source.instruction_slugs || source.instructionSlugs),
    args,
  };
}

function cleanPlanContent(record, item) {
  const steps = Array.isArray(record.steps)
    ? record.steps.map((step, index) => normalizeStep(step, index + 1))
    : [];

  return {
    version: Number(record.version || 1),
    label: String(record.label || item.slug),
    slug: item.slug,
    description: String(record.description || ''),
    step_count: steps.length,
    preflight: record.preflight && typeof record.preflight === 'object'
      ? record.preflight
      : { clean: true, warnings: [] },
    steps,
    source: {
      origin: 'obsidian.upload-plans',
      path: item.path,
      uploaded_at: item.uploadedAt,
      source_sha256: item.sourceSha256,
    },
  };
}

function loadPlanItems({ root, script, force = false }) {
  const items = [];

  for (const file of planJsonFiles(root)) {
    try {
      const record = readPlanJson(file);

      if (!isPlanUploadRecord(record)) {
        continue;
      }

      if (!planBelongsToRoot(record, root, file)) {
        continue;
      }

      if (!force && record.pending_upload !== true) {
        continue;
      }

      const recordIdentity = planRecordIdentity(record);

      items.push({
        order: items.length + 1,
        slug: recordIdentity,
        prefix: slugPrefix(recordIdentity) || 'plan',
        recordType: 'plan',
        path: file,
        basename: path.basename(file),
        label: record.label || recordIdentity,
        record,
        sourceSha256: sha256(JSON.stringify(record)),
      });
    } catch (error) {
      info(script, `ERROR: ${file}: ${error.message || error}`);
    }
  }

  return dropDuplicatePlanItems({ items, script });
}

function dropDuplicatePlanItems({ items, script }) {
  const bySlug = new Map();
  const duplicates = new Map();

  for (const item of items) {
    const existing = bySlug.get(item.slug);

    if (!existing) {
      bySlug.set(item.slug, item);
      continue;
    }

    const list = duplicates.get(item.slug) || [existing];
    list.push(item);
    duplicates.set(item.slug, list);
  }

  if (duplicates.size === 0) return items;

  const duplicateSlugs = new Set(duplicates.keys());

  for (const [slug, records] of duplicates.entries()) {
    info(script, `ERROR: duplicate plan slug skipped: ${slug}`);

    for (const record of records) {
      info(script, `ERROR:   ${record.path}`);
    }
  }

  return items.filter((item) => !duplicateSlugs.has(item.slug));
}

function planUploadRecord({ item, uploadedAt }) {
  const uploadItem = {
    ...item,
    uploadedAt,
  };

  return {
    record_type: 'plan',
    record_identity: item.slug,
    record_content: cleanPlanContent(item.record, uploadItem),
  };
}

function markPlanUploaded(item, uploadedAt) {
  const record = {
    ...item.record,
    pending_upload: false,
    uploaded_at: uploadedAt,
  };

  fs.writeFileSync(item.path, `${JSON.stringify(record, null, 2)}\n`, 'utf8');
}

function logPlanUpload({ script, root, items, force }) {
  info(script, `vault: ${root}`);
  info(script, force ? 'selection: all local plan records (--force)' : 'selection: pending local plan records');
  info(script, `matched plans: ${items.length}`);

  for (const item of items) {
    const pending = item.record.pending_upload === true ? ' [pending]' : '';
    info(script, `  ${item.recordType.padEnd(11)} ${item.slug}  ${item.path}${pending}`);
  }
}

function runUploadPlans(config = {}) {
  const script = config.script || SCRIPT;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const items = loadPlanItems({ root, script, force: options.force });
  logPlanUpload({ script, root, items, force: options.force });

  if (items.length === 0) {
    info(script, options.force
      ? 'no local plans found'
      : 'no pending local plans found');
    return;
  }

  if (options.dryRun) {
    info(script, 'dry run: no NDJSON emitted and no plan upload state changed');
    return;
  }

  const uploadedAt = new Date().toISOString();
  let emitted = 0;

  for (const item of items) {
    try {
      process.stdout.write(`${JSON.stringify(planUploadRecord({ item, uploadedAt }))}\n`);
      emitted += 1;
    } catch (error) {
      info(script, `ERROR: ${item.path}: ${error.message || error}`);
    }
  }

  if (emitted === 0) {
    info(script, 'no valid plans to upload after skipping errors');
    process.exitCode = 1;
    return;
  }

  for (const item of items) {
    try {
      markPlanUploaded(item, uploadedAt);
    } catch (error) {
      info(script, `ERROR: ${item.path}: could not reset pending_upload: ${error.message || error}`);
    }
  }

  info(script, `emitted ${emitted} plan record(s); reset pending_upload on local plan JSON`);
}

module.exports = {
  runUploadPlans,
  loadPlanItems,
  planUploadRecord,
  cleanPlanContent,
  normalizeStep,
};

if (require.main === module) {
  runUploadPlans();
}
