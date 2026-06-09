'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail, info } = require('./command');
const { sha256 } = require('./records');
const { readVaultFile, assertVaultRoot, vaultFileExists } = require('./selection');
const { runPandocUpload } = require('./pandoc-upload');

const { getGitRoot } = require('../../lib/git');
const { getFrontmatterTextFromMarkdown } = require('../../lib/markdown');
const { buildSlugPathMap } = require('../../lib/rg');

const SCRIPT = 'upload-prompts';
const DEFAULTS = ['upload_prompt'];

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH]

Behavior:
  Reads the current local run dispatch manifest, resolves each prompt slug
  against the active vault, and streams each prompt through Pandoc.

Options:
  -n, --dry-run      Show resolved prompt records; do not emit NDJSON.
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
  manifest.filepath = manifest.filepath || filepath;

  const manifestType = manifest.type || manifest.manifest_type || manifest.record_type;

  if (manifestType && manifestType !== 'run_dispatch_manifest') {
    fail(script, `manifest type is ${manifestType}, expected run_dispatch_manifest`);
  }

  return manifest;
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
      row.call_slug ||
      row.record_identity ||
      row.slug ||
      row.prompt;

    const planSlug =
      row.plan_slug ||
      row.job_slug ||
      row.plan ||
      manifest.plan_slug ||
      manifest.job_slug ||
      manifest.plan?.slug;

    return {
      ...row,
      index: row.index || index + 1,
      prompt_slug: promptSlug,
      call_slug: row.call_slug || promptSlug,
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
  if (!slug) fail(script, `call ${call.index || '?'} is missing prompt_slug`);

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

    return {
      ...call,
      path: resolvedPath,
      filename: call.filename || path.basename(resolvedPath),
      prompt_slug: call.prompt_slug || currentSlug,
      call_slug: call.call_slug || call.prompt_slug || currentSlug,
    };
  });
}

function buildPromptMetadata({ root, manifest, call, markdown, uploadedAt }) {
  const currentSlug = getFrontmatterTextFromMarkdown(markdown, 'slug');
  const callSlug = call.call_slug || call.prompt_slug || currentSlug;
  const planSlug = call.plan_slug || manifest.plan?.slug || manifest.plan_slug || manifest.job_slug;

  return {
    slug: callSlug,
    record_identity: callSlug,
    record_type: 'prompt',
    plan_slug: planSlug,
    source: {
      origin: 'obsidian.upload-prompts',
      vault_root: root,
      path: call.path,
      filename_hint: call.filename || path.basename(call.path),
      markdown_sha256: sha256(markdown),
      uploaded_at: uploadedAt,
      run_manifest: manifest.filepath || '',
      run_slug: manifest.slug || '',
      run_label: manifest.label || '',
      call_index: call.index || null,
    },
  };
}

function logPlan({ script, root, manifest, calls }) {
  info(script, `vault: ${root}`);
  info(script, `workflow: ${workflowDir(root)}`);
  info(script, `manifest: ${manifest.filepath}`);
  info(script, `pending prompt records: ${calls.length}`);

  for (const call of calls) {
    info(script, `  ${call.call_slug || call.prompt_slug || 'no-slug'}  ${call.plan_slug || 'no-plan'}  ${call.path}`);
  }
}

function runUploadPrompts(config = {}) {
  const script = config.script || SCRIPT;
  const defaults = config.defaults || DEFAULTS;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const manifest = loadDispatchManifest({ options, root, script });
  const calls = resolveCalls({ root, manifest, script });

  if (calls.length === 0) {
    info(script, 'no prompt records in dispatch manifest');
    return;
  }

  logPlan({ script, root, manifest, calls });

  if (options.dryRun) {
    info(script, 'dry run: no NDJSON emitted');
    return;
  }

  for (const call of calls) {
    const uploadedAt = new Date().toISOString();
    const markdown = readVaultFile(root, call.path);

    try {
      runPandocUpload({
        cwd: root,
        input: call.path,
        defaults,
        metadata: buildPromptMetadata({
          root,
          manifest,
          call,
          markdown,
          uploadedAt,
        }),
      });
    } catch (error) {
      fail(script, `${call.path}: upload failed: ${error.message || error}`);
    }
  }

  info(script, `emitted prompt records: ${calls.length}`);
}

module.exports = { main: runUploadPrompts, runUploadPrompts };

if (require.main === module) {
  runUploadPrompts();
}