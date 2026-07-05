'use strict';

const path = require('node:path');

const { fail, info } = require('./command');
const { readVaultFile, assertVaultRoot, vaultFileExists } = require('./selection');
const { runPandocUpload } = require('./pandoc-upload');
const {
  loadRunManifest,
  markCallUploaded,
  markCallUploadError,
  pendingRunCalls,
  writeRunManifest,
} = require('./run-manifest');

const { getGitRoot } = require('../../lib/git');
const { getFrontmatterTextFromMarkdown } = require('../../lib/markdown');
const { buildSlugPathMap } = require('../../lib/rg');

const SCRIPT = 'dispatch-run';
const DEFAULTS = ['upload_prompt'];

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH]

Behavior:
  Reads the current local run dispatch manifest, resolves each prompt slug
  against the active vault, and runs each Markdown prompt through Pandoc
  with record_plan supplied as metadata.

  Pandoc emits the final NDJSON record. Intended use: ${script} | asc enqueue

Options:
  -n, --dry-run      Print resolved records to stderr; do not emit NDJSON.
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

function loadDispatchManifest({ options, root, script }) {
  return loadRunManifest({ options, root, script });
}

function firstArray(...values) {
  for (const value of values) {
    if (Array.isArray(value)) return value;
  }
  return [];
}

function manifestRows(manifest) {
  if (manifest.type === 'run_manifest' || manifest.type === 'run_dispatch_manifest') {
    return pendingRunCalls(manifest);
  }

  return firstArray(
    manifest.prompt_plan_pairs,
    manifest.promptPlanPairs,
    manifest.slug_pairs,
    manifest.pairs,
    manifest.calls,
    manifest.items,
    manifest.records,
    manifest.dispatch
  ).filter((row) => String(row.upload_status || 'pending') === 'pending');
}

function normalizePromptPlanPairs(manifest) {
  const rows = manifestRows(manifest);

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
      ...row,
      index: row.index || index + 1,
      prompt_slug: promptSlug,
      call_slug: row.call_slug || row.callSlug || promptSlug,
      plan_slug: planSlug,
    };
  });
}

function duplicateMessage(records) {
  return records.map((record) => `${record.slug} ${record.path}:${record.lineNumber}`).join('\n');
}

function resolveCallPath({ root, call, slugMap, duplicates, script }) {
  if (call.path) {
    if (!call.path.endsWith('.md')) fail(script, `${call.path}: not a Markdown file`);
    if (!vaultFileExists(root, call.path)) fail(script, `${call.path}: file not found in active vault`);
    return call.path;
  }

  const slug = call.prompt_slug || call.call_slug;
  if (!slug) fail(script, `record ${call.index || '?'} is missing prompt_slug`);

  if (duplicates.has(slug)) {
    fail(script, `${slug}: prompt slug is not unique:\n${duplicateMessage(duplicates.get(slug))}`);
  }

  const record = slugMap.get(slug);
  if (!record) fail(script, `${slug}: prompt slug not found in active vault`);

  return record.path;
}

function resolveCalls({ root, manifest, script }) {
  const { bySlug, duplicates } = buildSlugPathMap({ root });

  return normalizePromptPlanPairs(manifest).map((call) => {
    if (!call.plan_slug) {
      fail(script, `${call.prompt_slug || call.call_slug || call.index || '?'}: missing plan_slug`);
    }

    const resolvedPath = resolveCallPath({
      root,
      call,
      slugMap: bySlug,
      duplicates,
      script,
    });

    const markdown = readVaultFile(root, resolvedPath);
    const currentSlug = getFrontmatterTextFromMarkdown(markdown, 'slug');

    if (call.prompt_slug && currentSlug && call.prompt_slug !== currentSlug) {
      fail(script, `${resolvedPath}: slug mismatch: manifest=${call.prompt_slug} file=${currentSlug}`);
    }

    const callSlug = call.call_slug || call.prompt_slug || currentSlug;
    if (!callSlug) fail(script, `${resolvedPath}: missing slug`);

    return {
      ...call,
      path: resolvedPath,
      filename: call.filename || path.basename(resolvedPath),
      prompt_slug: call.prompt_slug || currentSlug,
      call_slug: callSlug,
    };
  });
}

function dispatchPandocRecord({ root, call, defaults }) {
  runPandocUpload({
    cwd: root,
    input: call.path,
    defaults,
    metadata: {
      record_plan: call.plan_slug,
    },
  });
}

function logPlan({ script, root, manifest, calls }) {
  info(script, `vault: ${root}`);
  info(script, `workflow: ${workflowDir(root)}`);
  info(script, `manifest: ${manifest.filepath}`);
  info(script, `enqueue records: ${calls.length}`);

  for (const call of calls) {
    info(script, `  ${call.call_slug || call.prompt_slug || 'no-slug'}  ${call.plan_slug || 'no-plan'}  ${call.path}`);
  }
}

function runDispatchRun(config = {}) {
  const script = config.script || SCRIPT;
  const defaults = config.defaults || DEFAULTS;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const manifest = loadDispatchManifest({ options, root, script });
  const calls = resolveCalls({ root, manifest, script });

  if (calls.length === 0) {
    info(script, 'no pending enqueue records in dispatch manifest');
    return;
  }

  logPlan({ script, root, manifest, calls });

  if (options.dryRun) {
    info(script, 'dry run: no NDJSON emitted');
    return;
  }

  const uploadedAt = new Date().toISOString();
  let emitted = 0;

  for (const call of calls) {
    try {
      dispatchPandocRecord({ root, call, defaults });
      markCallUploaded({ manifest, call, uploadedAt });
      emitted += 1;
    } catch (error) {
      markCallUploadError({ manifest, call, error });
      writeRunManifest(manifest.filepath, manifest, script);
      fail(script, `${call.path}: dispatch failed: ${error.message || error}`);
    }
  }

  writeRunManifest(manifest.filepath, manifest, script);
  info(script, `emitted enqueue records: ${emitted}`);
}

module.exports = {
  main: runDispatchRun,
  runDispatchRun,
  normalizePromptPlanPairs,
  resolveCalls,
  dispatchPandocRecord,
};

if (require.main === module) {
  runDispatchRun();
}
