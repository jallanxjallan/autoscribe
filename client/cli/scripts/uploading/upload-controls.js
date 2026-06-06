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
const { getFrontmatterTextFromMarkdown, stripFrontmatter } = require('../../lib/markdown');
const { slugPrefix, assertUniqueSlugRecords } = require('../../lib/slug');
const {
  getGitRoot,
  lastCommitForPath,
  commitFiles,
} = require('../../lib/git');

const SCRIPT = 'upload-controls';
const OPERATION = 'control-status';
const QUERY_NAME = 'Control Status';
const DEFAULT_MAX_MANIFEST_AGE_SECONDS = 300;
const DEFAULTS = ['upload_control'];

const CONTROL_TYPES = {
  drv: 'driver',
  ins: 'instruction',
};

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH] [--allow-stale-manifest]
          [--max-age-seconds N]

Behavior:
  Reads the saved Control Status selection manifest for the active vault,
  verifies every selected Markdown file still has a drv.* or ins.* slug,
  commits exactly those selected files with --allow-empty, and streams one
  Pandoc-emitted NDJSON record per selected control file.

  Jobs are no longer uploaded here. job.* files are rejected.

Options:
  -n, --dry-run              Show what would be uploaded; do not commit or emit NDJSON.
  --manifest PATH            Use this manifest instead of the active-vault Control Status manifest.
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

function getControlManifest({ options, root, script }) {
  return getManifest({
    options,
    root,
    script,
    operation: OPERATION,
    queryName: QUERY_NAME,
  });
}

function recordTypeForPrefix(prefix) {
  return CONTROL_TYPES[prefix] || '';
}

function contentSha256(markdown) {
  return sha256(stripFrontmatter(markdown).trim());
}

function firstNonBlank(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim();
    }
  }

  return '';
}

function unquoteYamlScalar(value) {
  const text = String(value || '').trim();

  if (
    (text.startsWith('"') && text.endsWith('"')) ||
    (text.startsWith("'") && text.endsWith("'"))
  ) {
    return text.slice(1, -1);
  }

  return text;
}

function frontmatterText(markdown) {
  const text = String(markdown || '');

  if (!text.startsWith('---')) {
    return '';
  }

  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  return match ? match[1] : '';
}

function parseScalarLines(text, { topLevelOnly = false } = {}) {
  const out = {};
  const lines = String(text || '').split(/\r?\n/);

  for (const line of lines) {
    if (!line.trim() || line.trim().startsWith('#')) {
      continue;
    }

    if (topLevelOnly && /^\s/.test(line)) {
      continue;
    }

    const match = line.match(/^\s*([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*$/);
    if (!match) {
      continue;
    }

    const [, key, rawValue] = match;

    if (!rawValue.trim()) {
      continue;
    }

    out[key] = unquoteYamlScalar(rawValue);
  }

  return out;
}

function findDriverSection(text) {
  const lines = String(text || '').split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const match = line.match(/^(\s*)(?:["']?driver:?["']?)\s*:\s*$/);

    if (!match) {
      continue;
    }

    const baseIndent = match[1].length;
    const section = [];

    for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
      const next = lines[cursor];

      if (!next.trim()) {
        if (section.length > 0) break;
        continue;
      }

      const indent = (next.match(/^\s*/) || [''])[0].length;

      if (indent <= baseIndent) {
        break;
      }

      section.push(next.slice(baseIndent + 1));
    }

    return section.join('\n');
  }

  return '';
}

function extractDriverConfigFromMarkdown(markdown) {
  const frontmatter = frontmatterText(markdown);
  const direct = parseScalarLines(frontmatter, { topLevelOnly: true });
  const sectionText = findDriverSection(frontmatter) || findDriverSection(markdown);
  const section = parseScalarLines(sectionText);
  const raw = { ...direct, ...section };

  const client = firstNonBlank(raw.client, raw.engine);
  const driverType = firstNonBlank(raw.driver_type, raw['driver-type'], raw.driverType, raw.engine);
  const args = {};
  const reserved = new Set([
    'type',
    'slug',
    'identifier',
    'identity',
    'control_prefix',
    'client',
    'engine',
    'driver_type',
    'driver-type',
    'driverType',
    'description',
    'assets',
    'source',
  ]);

  for (const [key, value] of Object.entries(raw)) {
    if (reserved.has(key)) {
      continue;
    }

    if (value !== undefined && value !== null && String(value).trim()) {
      args[key] = String(value).trim();
    }
  }

  return {
    client,
    driver_type: driverType,
    args,
  };
}

function hydrateControlItem({ root, row, script }) {
  const relPath = row.path;

  if (!relPath.endsWith('.md')) {
    fail(script, `${relPath}: not a Markdown file`);
  }

  if (!vaultFileExists(root, relPath)) {
    fail(script, `${relPath}: file not found in active vault`);
  }

  const markdown = readVaultFile(root, relPath);
  const slug = getFrontmatterTextFromMarkdown(markdown, 'slug');

  if (!slug) {
    fail(script, `${relPath}: missing frontmatter slug`);
  }

  if (row.slug && row.slug !== slug) {
    fail(script, `${relPath}: manifest slug differs from current file (${row.slug} -> ${slug})`);
  }

  const prefix = slugPrefix(slug);
  const recordType = recordTypeForPrefix(prefix);

  if (!recordType) {
    fail(script, `${relPath}: selected control slug must start with drv. or ins. (${slug})`);
  }

  return {
    order: Number.isFinite(Number(row.order)) ? Number(row.order) : 0,
    slug,
    prefix,
    recordType,
    path: relPath,
    name: row.name || path.basename(relPath),
    basename: row.basename || path.basename(relPath),
    content_sha256: contentSha256(markdown),
    previous_commit: lastCommitForPath({ root, path: relPath }),
    manifest_row: row,
  };
}

function preflightManifestControls({ root, manifest, script }) {
  const rows = uniqueManifestRows({
    manifest,
    script,
    queryName: QUERY_NAME,
  });

  if (rows.length === 0) {
    fail(script, 'Control Status manifest contains no selected control files');
  }

  const items = rows.map((row) => hydrateControlItem({ root, row, script }));

  assertUniqueSlugRecords(items, { label: 'control slug' });

  items.sort((a, b) => {
    const orderDiff = (a.order || 0) - (b.order || 0);
    if (orderDiff !== 0) return orderDiff;
    return a.path.localeCompare(b.path);
  });

  return items;
}

function commitControlFiles({ root, items, manifest }) {
  const stamp = formatFileStamp();
  const paths = items.map((item) => item.path);

  const counts = items.reduce((acc, item) => {
    acc[item.recordType] = (acc[item.recordType] || 0) + 1;
    return acc;
  }, {});

  const message = `UPLOAD controls: ${stamp}`;
  const body = [
    'Uploaded selected control files.',
    '',
    `Manifest: ${manifest.filepath || ''}`,
    `Manifest timestamp: ${manifestTimestamp(manifest) || ''}`,
    '',
    `Drivers: ${counts.driver || 0}`,
    `Instructions: ${counts.instruction || 0}`,
    '',
    'Control files:',
    ...items.map((item) => `- ${item.slug}  ${item.path}`),
  ].join('\n');

  return commitFiles({
    root,
    paths,
    message,
    body,
    allowEmpty: true,
  });
}

function buildControlUploadMetadata({ root, item, manifest, uploadCommit, uploadedAt, script }) {
  const markdown = readVaultFile(root, item.path);
  const metadata = {
    slug: item.slug,
    identifier: item.slug,
    type: item.recordType,
    control_prefix: item.prefix,
    source: {
      origin: 'obsidian.upload-controls',
      vault_root: root,
      path: item.path,
      filename_hint: item.basename || path.basename(item.path),
      previous_commit: item.previous_commit,
      upload_commit: uploadCommit,
      uploaded_at: uploadedAt,
      content_sha256: item.content_sha256,
      control_manifest: manifest.filepath || '',
      control_manifest_timestamp: manifestTimestamp(manifest),
      control_manifest_operation: manifest.operation || OPERATION,
      selection_order: item.order,
    },
  };

  if (item.recordType === 'driver') {
    const driver = extractDriverConfigFromMarkdown(markdown);

    if (!driver.client) {
      fail(script, `${item.path}: driver control is missing client or engine`);
    }

    if (!driver.driver_type) {
      fail(script, `${item.path}: driver control is missing driver_type, driver-type, or engine`);
    }

    metadata.client = driver.client;
    metadata.driver_type = driver.driver_type;
    metadata.args = driver.args;
  }

  return metadata;
}

function logPlan({ script, root, manifest, items }) {
  const counts = items.reduce((acc, item) => {
    acc[item.recordType] = (acc[item.recordType] || 0) + 1;
    return acc;
  }, {});

  info(script, `vault: ${root}`);
  info(script, `manifest: ${manifest.filepath}`);

  const timestamp = manifestTimestamp(manifest);
  if (timestamp) info(script, `manifest timestamp: ${timestamp}`);

  info(
    script,
    `matched selected control files: ${items.length} (${counts.driver || 0} drivers, ${counts.instruction || 0} instructions)`
  );

  for (const item of items) {
    info(script, `  ${item.recordType.padEnd(11)} ${item.slug}  ${item.path}`);
  }
}

function runUploadControls(config = {}) {
  const script = config.script || SCRIPT;
  const defaults = config.defaults || DEFAULTS;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const manifest = getControlManifest({ options, root, script });
  const items = preflightManifestControls({ root, manifest, script });

  logPlan({ script, root, manifest, items });

  if (options.dryRun) {
    info(script, 'dry run: no commit made and no NDJSON emitted');
    return;
  }

  const uploadedAt = new Date().toISOString();
  const uploadCommit = commitControlFiles({ root, items, manifest });

  info(script, `committed control upload custody: ${uploadCommit}`);

  for (const item of items) {
    runPandocUpload({
      cwd: root,
      input: item.path,
      defaults,
      metadata: buildControlUploadMetadata({
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
  runUploadControls,
  contentSha256,
  hydrateControlItem,
  preflightManifestControls,
};

if (require.main === module) {
  runUploadControls();
}
