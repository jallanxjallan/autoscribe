'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail, info } = require('./command');
const { sha256 } = require('./records');
const { readVaultFile, assertVaultRoot, vaultFileExists } = require('./selection');
const { runPandocCapture } = require('./pandoc-upload');

const { getGitRoot } = require('../../lib/git');
const { getFrontmatterTextFromMarkdown } = require('../../lib/markdown');
const { buildSlugPathMap } = require('../../lib/rg');

const SCRIPT = 'dispatch-run';
const DEFAULTS = ['upload_prompt'];

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH]

Behavior:
  Reads the current local run dispatch manifest, resolves each content slug
  against the active vault, renders the Markdown through Pandoc, and emits
  enqueue NDJSON records suitable for: ${script} | asc enqueue

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

  const manifestType = 'run_dispatch_manifest' 
  // payload.type || payload.manifest_type || payload.record_type;

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

function buildDispatchRecord({ root, manifest, call, markdown, rendered, dispatchedAt }) {
  return {
    record_type: 'call',
    record_identity: call.call_slug,
    plan_slug: call.plan_slug,
    record_content: rendered,
    source: {
      origin: 'obsidian.dispatch-run',
      vault_root: root,
      path: call.path,
      filename_hint: call.filename || path.basename(call.path),
      markdown_sha256: sha256(markdown),
      rendered_sha256: sha256(rendered),
      dispatched_at: dispatchedAt,
      run_manifest: manifest.filepath || '',
      run_slug: manifest.slug || '',
      run_label: manifest.label || '',
      call_index: call.index || null,
    },
  };
}

function renderDispatchRecord({ root, manifest, call, defaults, script }) {
  const markdown = readVaultFile(root, call.path);
  const dispatchedAt = new Date().toISOString();

  let rendered = '';
  try {
    rendered = runPandocCapture({
      cwd: root,
      input: call.path,
      defaults,
      metadata: {
        record_identity: call.call_slug,
        record_type: 'call',
      },
    });
  } catch (error) {
    fail(script, `${call.path}: pandoc render failed: ${error.message || error}`);
  }

  return buildDispatchRecord({
    root,
    manifest,
    call,
    markdown,
    rendered,
    dispatchedAt,
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
    info(script, 'no enqueue records in dispatch manifest');
    return;
  }

  logPlan({ script, root, manifest, calls });

  if (options.dryRun) {
    info(script, 'dry run: no NDJSON emitted');
    return;
  }

  for (const call of calls) {
    const record = renderDispatchRecord({ root, manifest, call, defaults, script });
    process.stdout.write(`${JSON.stringify(record)}\n`);
  }

  info(script, `emitted enqueue records: ${calls.length}`);
}

module.exports = {
  main: runDispatchRun,
  runDispatchRun,
  normalizePromptPlanPairs,
  resolveCalls,
  renderDispatchRecord,
};

if (require.main === module) {
  runDispatchRun();
}
