'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail, info } = require('./command');
const { getGitRoot } = require('../../lib/git');
const { assertVaultRoot } = require('./selection');

const SCRIPT = 'dispatch-run';

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH]

Behavior:
  Reads the current local run dispatch manifest and emits NDJSON slug-pair
  records suitable for: ${script} | asc enqueue

Options:
  -n, --dry-run      Print resolved pairs to stderr; do not emit NDJSON.
  --manifest PATH    Use this manifest instead of .autoscribe/workflow/runs/current-run.json.
  -h, --help         Show this help.
`);
}

function parseArgs(argv, script) {
  const options = { dryRun: false, manifestPath: '' };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === '--dry-run' || arg === '-n') {
      options.dryRun = true;
    } else if (arg === '--manifest') {
      options.manifestPath = argv[++i] || '';
      if (!options.manifestPath) fail(script, '--manifest requires a path');
    } else if (arg.startsWith('--manifest=')) {
      options.manifestPath = arg.slice('--manifest='.length);
    } else if (arg === '--help' || arg === '-h') {
      usage(script);
      process.exit(0);
    } else {
      fail(script, `unknown argument: ${arg}`);
    }
  }

  return options;
}

function workflowDir(root) {
  return process.env.AUTOSCRIBE_WORKFLOW_DIR ||
    path.join(root, '.autoscribe', 'workflow');
}

function defaultManifestPath(root) {
  return path.join(workflowDir(root), 'runs', 'current-run.json');
}

function readJsonFile(filepath, script) {
  try {
    return JSON.parse(fs.readFileSync(filepath, 'utf8'));
  } catch (error) {
    fail(script, `${filepath}: could not read JSON: ${error.message || error}`);
  }
}

function loadDispatchManifest({ options, root, script }) {
  const filepath = path.resolve(root, options.manifestPath || defaultManifestPath(root));
  const manifest = readJsonFile(filepath, script);
  const payload = Array.isArray(manifest) ? { slug_pairs: manifest } : { ...manifest };
  payload.filepath = payload.filepath || filepath;

  const manifestType = payload.type || payload.manifest_type || payload.record_type;

  if (manifestType && manifestType !== 'run_dispatch_manifest') {
    fail(script, `manifest type is ${manifestType}, expected run_dispatch_manifest`);
  }

  return payload;
}

function firstArray(...values) {
  for (const value of values) {
    if (Array.isArray(value)) return value;
  }
  return [];
}

function normalizePromptPlanPairs(manifest) {
  const rows = firstArray(
    manifest.prompt_plan_pairs,
    manifest.promptPlanPairs,
    manifest.slug_pairs,
    manifest.pairs,
    manifest.calls,
    manifest.items,
    manifest.records,
    manifest.dispatch
  );

  return rows.map((row, index) => {
    const promptSlug =
      row.prompt_slug ||
      row.promptSlug ||
      row.call_slug ||
      row.callSlug ||
      row.record_identity ||
      row.recordIdentity ||
      row.slug ||
      row.prompt;

    const planSlug =
      row.plan_slug ||
      row.planSlug ||
      row.job_slug ||
      row.jobSlug ||
      row.plan ||
      manifest.plan_slug ||
      manifest.planSlug ||
      manifest.job_slug ||
      manifest.jobSlug ||
      manifest.plan?.slug;

    return {
      index: row.index || index + 1,
      prompt_slug: promptSlug,
      plan_slug: planSlug,
    };
  });
}

function validateSlug(value, fieldName, index, script) {
  if (typeof value !== 'string' || !value.trim()) {
    fail(script, `row ${index}: missing ${fieldName}`);
  }
  return value.trim();
}

function resolvePairs({ manifest, script }) {
  return normalizePromptPlanPairs(manifest).map((row) => ({
    prompt_slug: validateSlug(row.prompt_slug, 'prompt_slug', row.index, script),
    plan_slug: validateSlug(row.plan_slug, 'plan_slug', row.index, script),
  }));
}

function logPlan({ script, root, manifest, pairs }) {
  info(script, `vault: ${root}`);
  info(script, `workflow: ${workflowDir(root)}`);
  info(script, `manifest: ${manifest.filepath}`);
  info(script, `enqueue records: ${pairs.length}`);

  for (const pair of pairs) {
    info(script, `  ${pair.prompt_slug}  ${pair.plan_slug}`);
  }
}

function runDispatchRun(config = {}) {
  const script = config.script || SCRIPT;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const manifest = loadDispatchManifest({ options, root, script });
  const pairs = resolvePairs({ manifest, script });

  if (pairs.length === 0) {
    info(script, 'no enqueue records in dispatch manifest');
    return;
  }

  logPlan({ script, root, manifest, pairs });

  if (options.dryRun) {
    info(script, 'dry run: no NDJSON emitted');
    return;
  }

  for (const pair of pairs) {
    process.stdout.write(`${JSON.stringify(pair)}\n`);
  }

  info(script, `emitted enqueue records: ${pairs.length}`);
}

module.exports = {
  main: runDispatchRun,
  runDispatchRun,
  normalizePromptPlanPairs,
  resolvePairs,
};

if (require.main === module) {
  runDispatchRun();
}
