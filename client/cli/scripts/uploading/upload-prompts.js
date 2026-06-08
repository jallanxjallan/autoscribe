'use strict';

const path = require('node:path');

const { fail, info } = require('./command');
const { sha256 } = require('./records');
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

const SCRIPT = 'upload-prompts';
const DEFAULTS = ['upload_prompt'];

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH]

Behavior:
  Reads the current local run manifest, streams each pending prompt through
  Pandoc, and rewrites the manifest with optimistic upload_status updates.

  Stdout is reserved for Pandoc-emitted NDJSON records only.
  Status messages go to stderr.

Options:
  -n, --dry-run      Show pending prompt records; do not emit NDJSON or rewrite manifest.
  --manifest PATH    Use this run manifest instead of runs/current-run.json.
  -h, --help         Show this help.
`);
}

function parseArgs(argv, script) {
  const options = {
    dryRun: false,
    manifestPath: '',
  };

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

function buildPromptMetadata({ root, manifest, call, markdown, uploadedAt }) {
  const currentSlug = getFrontmatterTextFromMarkdown(markdown, 'slug');
  const callSlug = call.call_slug || call.prompt_slug || currentSlug;
  const planSlug = call.plan_slug || manifest.plan?.slug || manifest.plan_slug;

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

function assertPendingCall({ root, call, script }) {
  if (!call.path) {
    fail(script, `call ${call.index || call.call_slug || '?'} is missing path`);
  }

  if (!call.path.endsWith('.md')) {
    fail(script, `${call.path}: not a Markdown file`);
  }

  if (!vaultFileExists(root, call.path)) {
    fail(script, `${call.path}: file not found in active vault`);
  }

  const planSlug = call.plan_slug;
  if (!planSlug) {
    fail(script, `${call.path}: missing plan_slug`);
  }
}

function logPlan({ script, root, manifest, calls }) {
  info(script, `vault: ${root}`);
  info(script, `manifest: ${manifest.filepath}`);
  info(script, `plan: ${manifest.plan?.slug || manifest.plan_slug || calls[0]?.plan_slug || ''}`);
  info(script, `pending prompt records: ${calls.length}`);

  for (const call of calls) {
    info(script, `  ${call.call_slug || call.prompt_slug || 'no-slug'}  ${call.path}`);
  }
}

function runUploadPrompts(config = {}) {
  const script = config.script || SCRIPT;
  const defaults = config.defaults || DEFAULTS;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const manifest = loadRunManifest({ options, root, script });
  const calls = pendingRunCalls(manifest);

  if (calls.length === 0) {
    info(script, 'no pending prompt records');
    return;
  }

  for (const call of calls) {
    assertPendingCall({ root, call, script });
  }

  logPlan({ script, root, manifest, calls });

  if (options.dryRun) {
    info(script, 'dry run: no NDJSON emitted and manifest not rewritten');
    return;
  }

  for (const call of calls) {
    const uploadedAt = new Date().toISOString();

    try {
      const markdown = readVaultFile(root, call.path);

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

      markCallUploaded({ manifest, call, uploadedAt });
      writeRunManifest(manifest.filepath, manifest, script);
    } catch (error) {
      markCallUploadError({ manifest, call, error });
      writeRunManifest(manifest.filepath, manifest, script);
      fail(script, `${call.path}: upload failed: ${error.message || error}`);
    }
  }

  info(script, `marked uploaded: ${calls.length}`);
}

module.exports = { main: runUploadPrompts, runUploadPrompts };

if (require.main === module) {
  runUploadPrompts();
}
