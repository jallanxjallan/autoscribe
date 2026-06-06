'use strict';

const path = require('node:path');

const { fail, info, parseManifestCommandArgs } = require('./command');
const { getManifest, manifestTimestamp, uniqueManifestRows } = require('./manifest');
const {
  assertVaultRoot,
  readVaultFile,
  vaultFileExists,
} = require('./selection');
const { sha256 } = require('./records');
const { runPandocUpload } = require('./pandoc-upload');

const { formatFileStamp } = require('../../lib/json-io');
const { isPublicVaultPath } = require('../../lib/query-paths');
const { getFrontmatterTextFromMarkdown } = require('../../lib/markdown');
const { slugPrefix, assertUniqueSlugRecords } = require('../../lib/slug');
const {
  getGitRoot,
  hasEverBeenCommitted,
  lastCommitForPath,
  commitFiles,
} = require('../../lib/git');

const SCRIPT = 'enqueue-prompts';
const OPERATION = 'enqueue-jobs';
const QUERY_NAME = 'Enqueue Jobs';
const DEFAULT_MAX_MANIFEST_AGE_SECONDS = 120;
const DEFAULTS = ['upload_prompt'];

const NON_PROMPT_PREFIXES = new Set(['drv', 'ins', 'job', 'gbl', 'cxt', 'spc']);

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH] [--allow-stale-manifest]
          [--max-age-seconds N]

Behavior:
  Reads the saved Enqueue Jobs selection manifest for the active vault,
  verifies every selected Markdown prompt file has previously been committed,
  commits exactly those selected files with --allow-empty, and streams one
  Pandoc-emitted NDJSON record per selected prompt file.

Options:
  -n, --dry-run              Show what would be enqueued; do not commit or emit NDJSON.
  --manifest PATH            Use this manifest instead of the active-vault Enqueue Jobs manifest.
  --allow-stale-manifest     Disable the manifest freshness guard.
  --max-age-seconds N        Freshness limit for manifest. Default: ${DEFAULT_MAX_MANIFEST_AGE_SECONDS}.
  -h, --help                 Show this help.
`);
}

function parseArgs(argv, script) {
  return parseManifestCommandArgs({
    argv,
    script,
    defaultMaxAgeSeconds: DEFAULT_MAX_MANIFEST_AGE_SECONDS,
    usage,
  });
}

function getEnqueueManifest({ options, root, script }) {
  return getManifest({
    options,
    root,
    script,
    operation: OPERATION,
    queryName: QUERY_NAME,
  });
}

function preflightManifestPrompts({ root, manifest, script }) {
  const rows = uniqueManifestRows({
    manifest,
    script,
    queryName: QUERY_NAME,
  });

  if (rows.length === 0) {
    fail(script, 'Enqueue Jobs manifest contains no selected prompt files');
  }

  const items = [];
  const errors = [];
  const jobSlugs = new Set();

  for (const row of rows) {
    const relPath = row.path;

    try {
      const jobSlug = row.job_slug;

      if (!jobSlug) {
        errors.push(`${relPath}: missing job_slug`);
        continue;
      }

      if (slugPrefix(jobSlug) !== 'job') {
        errors.push(`${relPath}: job_slug must start with job. (${jobSlug})`);
        continue;
      }

      if (!relPath.endsWith('.md')) {
        errors.push(`${relPath}: not a Markdown file`);
        continue;
      }

      if (!isPublicVaultPath(relPath)) {
        errors.push(`${relPath}: files under _* folders are not enqueueable prompts`);
        continue;
      }

      if (!vaultFileExists(root, relPath)) {
        errors.push(`${relPath}: file not found in active vault`);
        continue;
      }

      if (!hasEverBeenCommitted({ root, path: relPath })) {
        errors.push(`${relPath}: has never been committed; commit once before processing`);
        continue;
      }

      const markdown = readVaultFile(root, relPath);
      const slug = getFrontmatterTextFromMarkdown(markdown, 'slug');

      if (!slug) {
        errors.push(`${relPath}: missing frontmatter slug`);
        continue;
      }

      if (row.slug !== slug) {
        errors.push(`${relPath}: manifest slug differs from current file (${row.slug || 'missing'} -> ${slug})`);
        continue;
      }

      const prefix = slugPrefix(slug);

      if (NON_PROMPT_PREFIXES.has(prefix)) {
        errors.push(`${relPath}: ${prefix}. is not a prompt/content prefix`);
        continue;
      }

      jobSlugs.add(jobSlug);

      items.push({
        order: Number.isFinite(Number(row.order)) ? Number(row.order) : items.length + 1,
        slug,
        job_slug: jobSlug,
        prefix,
        path: relPath,
        basename: path.basename(relPath),
        previous_commit: lastCommitForPath({ root, path: relPath }),
      });
    } catch (error) {
      errors.push(`${relPath}: ${error.message}`);
    }
  }

  if (errors.length > 0) {
    fail(script, `enqueue prompt preflight failed:\n${errors.map((line) => `  - ${line}`).join('\n')}`);
  }

  assertUniqueSlugRecords(items, { label: 'prompt slug' });

  if (jobSlugs.size > 1) {
    fail(script, `manifest contains multiple job slugs; expected one: ${[...jobSlugs].join(', ')}`);
  }

  items.sort((a, b) => a.order - b.order || a.path.localeCompare(b.path));
  return items;
}

function commitPromptFiles({ root, items }) {
  const stamp = formatFileStamp();
  const paths = items.map((item) => item.path);
  const jobSlug = items[0]?.job_slug || 'job.unknown';
  const message = `ENQUEUE prompts: ${stamp}`;
  const body = [
    `Job: ${jobSlug}`,
    '',
    'Prompt files:',
    ...paths.map((itemPath) => `- ${itemPath}`),
  ].join('\n');

  const uploadCommit = commitFiles({
    root,
    paths,
    message,
    body,
    allowEmpty: true,
  });

  return { uploadCommit, message };
}

function buildPromptUploadMetadata({ root, item, manifest, uploadCommit, uploadedAt, script }) {
  const markdown = readVaultFile(root, item.path);
  const currentSlug = getFrontmatterTextFromMarkdown(markdown, 'slug');

  if (currentSlug !== item.slug) {
    fail(script, `${item.path}: slug changed during enqueue (${item.slug} -> ${currentSlug || 'missing'})`);
  }

  return {
    slug: item.slug,
    identifier: item.slug,
    type: 'prompt',
    job_slug: item.job_slug,
    source: {
      origin: 'obsidian.enqueue-prompts',
      vault_root: root,
      path: item.path,
      filename_hint: item.basename,
      previous_commit: item.previous_commit,
      upload_commit: uploadCommit,
      uploaded_at: uploadedAt,
      markdown_sha256: sha256(markdown),
      enqueue_manifest: manifest.filepath || '',
      enqueue_manifest_timestamp: manifestTimestamp(manifest),
      enqueue_manifest_operation: manifest.operation || OPERATION,
      selection_order: item.order,
    },
  };
}

function logPlan({ script, root, manifest, items }) {
  info(script, `vault: ${root}`);
  info(script, `manifest: ${manifest.filepath}`);

  const timestamp = manifestTimestamp(manifest);
  if (timestamp) info(script, `manifest timestamp: ${timestamp}`);

  info(script, `job: ${items[0]?.job_slug || ''}`);
  info(script, `matched selected prompt files: ${items.length}`);

  for (const item of items) {
    info(script, `  ${item.slug}  ${item.path}`);
  }
}

function runEnqueuePrompts(config = {}) {
  const script = config.script || SCRIPT;
  const defaults = config.defaults || DEFAULTS;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const manifest = getEnqueueManifest({ options, root, script });
  const items = preflightManifestPrompts({ root, manifest, script });

  logPlan({ script, root, manifest, items });

  if (options.dryRun) {
    info(script, 'dry run: no commit made and no NDJSON emitted');
    return;
  }

  const uploadedAt = new Date().toISOString();
  const { uploadCommit } = commitPromptFiles({ root, items });

  info(script, `committed prompt enqueue custody: ${uploadCommit}`);

  for (const item of items) {
    runPandocUpload({
      cwd: root,
      input: item.path,
      defaults,
      metadata: buildPromptUploadMetadata({
        root,
        item,
        manifest,
        uploadCommit,
        uploadedAt,
        script,
      }),
    });
  }
}

module.exports = {
  runEnqueuePrompts,
};

if (require.main === module) {
  runEnqueuePrompts();
}
