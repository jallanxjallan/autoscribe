'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { fail, info } = require('./command');
const {
  assertVaultRoot,
  readVaultFile,
  vaultFileExists,
  normalizeRelPath,
} = require('./selection');
const { sha256 } = require('./records');
const { runPandocUpload } = require('./pandoc-upload');

const { formatFileStamp } = require('../../lib/json-io');
const { getFrontmatterTextFromMarkdown, stripFrontmatter } = require('../../lib/markdown');
const { slugPrefix } = require('../../lib/slug');
const {
  getGitRoot,
  lastCommitForPath,
  commitFiles,
  listDirtyFiles,
} = require('../../lib/git');

const DEFAULTS = ['upload_control'];

const COMPONENTS = {
  drivers: {
    singular: 'driver',
    recordType: 'driver',
    prefixes: new Set(['drv']),
    label: 'drivers',
    requiresDriverConfig: true,
  },
  instructions: {
    singular: 'instruction',
    recordType: 'instruction',
    prefixes: new Set(['ins', 'gbl', 'cxt', 'spc']),
    label: 'instructions',
    requiresDriverConfig: false,
  },
  plans: {
    singular: 'plan',
    recordType: 'plan',
    prefixes: new Set(['plan']),
    label: 'plans',
    requiresDriverConfig: false,
  },
};

function usage(script, component) {
  if (component.recordType === 'plan') {
    console.error(`Usage:
  ${script} [--dry-run] [--force]

Behavior:
  Normal mode uploads local plan JSON records marked pending_upload=true.
  Plan records are read from the AutoScribe Obsidian workflow store, not from
  Markdown files in the vault and not from git dirty state.

  Force mode uploads every local plan JSON record for the active vault,
  regardless of pending_upload state.

  Human messages are written to stderr; valid plan records are emitted as
  clean NDJSON on stdout.

Options:
  -n, --dry-run              Show what would be uploaded; do not emit NDJSON or reset state.
  -f, --force                Upload all local plans for this vault.
  -h, --help                 Show this help.
`);
    return;
  }

  console.error(`Usage:
  ${script} [--dry-run] [--force]

Behavior:
  Normal mode uploads dirty Markdown files in the active vault whose frontmatter
  slug starts with ${[...component.prefixes].map((prefix) => `${prefix}.*`).join(' or ')}.
  Dirty means modified, added, renamed, copied, type-changed, unmerged, deleted,
  or untracked according to git status. Deleted files are ignored because they
  cannot be uploaded.

  Force mode uploads every Markdown file in the active vault whose frontmatter
  slug matches the ${component.singular} prefix, regardless of git state.

  Each matching file is prepared independently. Bad files are reported to
  stderr and skipped; valid files still emit clean NDJSON on stdout.

  After a non-dry valid upload selection is found, the valid files are committed
  with a timestamped message, then Pandoc emits one NDJSON record per uploaded
  ${component.singular} file.

Options:
  -n, --dry-run              Show what would be uploaded; do not commit or emit NDJSON.
  -f, --force                Upload all matching files, regardless of git state.
  -h, --help                 Show this help.
`);
}

function parseArgs(argv, script, component) {
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
      usage(script, component);
      process.exit(0);
    } else {
      fail(script, `unknown argument: ${arg}`);
    }
  }

  return options;
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

function shouldSkipPath(relPath) {
  const normalized = normalizeRelPath(relPath);
  return (
    !normalized.endsWith('.md') ||
    normalized.startsWith('.git/') ||
    normalized.startsWith('.obsidian/') ||
    normalized.startsWith('_control/')
  );
}

function walkMarkdownFiles(root, dir = root, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '.git' || entry.name === '.obsidian') {
      continue;
    }

    const fullPath = path.join(dir, entry.name);
    const relPath = normalizeRelPath(path.relative(root, fullPath));

    if (entry.isDirectory()) {
      walkMarkdownFiles(root, fullPath, out);
    } else if (entry.isFile() && !shouldSkipPath(relPath)) {
      out.push(relPath);
    }
  }

  return out;
}

function hydrateControlPath({ root, relPath, script, component, order = 0 }) {
  const normalizedPath = normalizeRelPath(relPath);

  if (shouldSkipPath(normalizedPath)) {
    return null;
  }

  if (!vaultFileExists(root, normalizedPath)) {
    return null;
  }

  const markdown = readVaultFile(root, normalizedPath);
  const slug = getFrontmatterTextFromMarkdown(markdown, 'slug');

  if (!slug) {
    return null;
  }

  const prefix = slugPrefix(slug);

  if (!component.prefixes.has(prefix)) {
    return null;
  }

  return {
    order,
    slug,
    prefix,
    recordType: component.recordType,
    path: normalizedPath,
    name: path.basename(normalizedPath),
    basename: path.basename(normalizedPath),
    content_sha256: contentSha256(markdown),
    previous_commit: lastCommitForPath({ root, path: normalizedPath }),
  };
}

function candidatePaths({ root, force }) {
  if (force) {
    return walkMarkdownFiles(root).sort((a, b) => a.localeCompare(b));
  }

  return listDirtyFiles({ root })
    .filter((relPath) => !shouldSkipPath(relPath))
    .sort((a, b) => a.localeCompare(b));
}

function discoverComponentItems({ root, script, componentName, force = false }) {
  const component = COMPONENTS[componentName];
  if (!component) fail(script, `unknown control component: ${componentName}`);

  const items = candidatePaths({ root, force })
    .map((relPath, index) => hydrateControlPath({
      root,
      relPath,
      script,
      component,
      order: index + 1,
    }))
    .filter(Boolean);

  return dropDuplicateSlugItems({ items, script, component });
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

function loadPlanItems({ root, script, force = false }) {
  const items = [];

  for (const file of planJsonFiles(root)) {
    try {
      const record = readPlanJson(file);

      if (!record || record.type !== 'plan' || !record.slug) {
        continue;
      }

      if (!planBelongsToRoot(record, root, file)) {
        continue;
      }

      if (!force && record.pending_upload !== true) {
        continue;
      }

      items.push({
        order: items.length + 1,
        slug: record.slug,
        prefix: slugPrefix(record.slug) || 'plan',
        recordType: 'plan',
        path: file,
        basename: path.basename(file),
        label: record.label || record.slug,
        record,
      });
    } catch (error) {
      info(script, `ERROR: ${file}: ${error.message || error}`);
    }
  }

  return dropDuplicateSlugItems({
    items,
    script,
    component: COMPONENTS.plans,
  });
}

function planUploadRecord({ root, item, uploadedAt, force }) {
  return {
    ...item.record,
    identifier: item.record.identifier || item.record.slug,
    control_prefix: item.record.control_prefix || item.prefix || slugPrefix(item.record.slug) || 'plan',
    source: {
      ...(item.record.source || {}),
      origin: 'obsidian.upload-plans',
      vault_root: root,
      path: item.path,
      filename_hint: item.basename || path.basename(item.path),
      uploaded_at: uploadedAt,
      selection_mode: force ? 'force-all-local-plans' : 'pending-upload-local-plans',
      selection_order: item.order,
    },
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

function logStoredPlanUpload({ script, root, items, force }) {
  info(script, `vault: ${root}`);
  info(script, force ? 'selection: all local plan records (--force)' : 'selection: pending local plan records');
  info(script, `matched plans: ${items.length}`);

  for (const item of items) {
    const pending = item.record.pending_upload === true ? ' [pending]' : '';
    info(script, `  ${item.recordType.padEnd(11)} ${item.slug}  ${item.path}${pending}`);
  }
}

function runUploadPlansFromStore({ script, options }) {
  const root = getGitRoot(process.cwd());
  assertVaultRoot({ root, script });

  const items = loadPlanItems({ root, script, force: options.force });
  logStoredPlanUpload({ script, root, items, force: options.force });

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
      process.stdout.write(`${JSON.stringify(planUploadRecord({
        root,
        item,
        uploadedAt,
        force: options.force,
      }))}\n`);
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

function dropDuplicateSlugItems({ items, script, component }) {
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

  if (duplicates.size === 0) {
    return items;
  }

  const duplicateSlugs = new Set(duplicates.keys());

  for (const [slug, records] of duplicates.entries()) {
    info(script, `ERROR: duplicate ${component.singular} slug skipped: ${slug}`);

    for (const record of records) {
      info(script, `ERROR:   ${record.path}`);
    }
  }

  return items.filter((item) => !duplicateSlugs.has(item.slug));
}

function commitComponentFiles({ root, items, component, force }) {
  const stamp = formatFileStamp();
  const paths = items.map((item) => item.path);

  const message = `UPLOAD ${component.label}: ${stamp}`;
  const body = [
    force
      ? `Force-uploaded matching ${component.label}.`
      : `Uploaded dirty matching ${component.label}.`,
    '',
    `${component.label[0].toUpperCase()}${component.label.slice(1)}: ${items.length}`,
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

function buildComponentUploadMetadata({ root, item, uploadCommit = '', uploadedAt, component, force }) {
  const markdown = readVaultFile(root, item.path);
  const metadata = {
    slug: item.slug,
    identifier: item.slug,
    type: item.recordType,
    control_prefix: item.prefix,
    source: {
      origin: `obsidian.upload-${component.label}`,
      vault_root: root,
      path: item.path,
      filename_hint: item.basename || path.basename(item.path),
      previous_commit: item.previous_commit,
      upload_commit: uploadCommit,
      uploaded_at: uploadedAt,
      content_sha256: item.content_sha256,
      selection_mode: force ? 'force-all-matching-prefix' : 'dirty-matching-prefix',
      selection_order: item.order,
    },
  };

  if (component.requiresDriverConfig) {
    const driver = extractDriverConfigFromMarkdown(markdown);

    if (!driver.client) {
      throw new Error('driver control is missing client or engine');
    }

    if (!driver.driver_type) {
      throw new Error('driver control is missing driver_type, driver-type, or engine');
    }

    metadata.client = driver.client;
    metadata.driver_type = driver.driver_type;
    metadata.args = driver.args;
  }

  return metadata;
}

function prepareUploadRecords({ root, items, script, component, force }) {
  const uploadedAt = new Date().toISOString();
  const records = [];

  for (const item of items) {
    try {
      records.push({
        item,
        metadata: buildComponentUploadMetadata({
          root,
          item,
          uploadedAt,
          component,
          force,
        }),
      });
    } catch (error) {
      info(script, `ERROR: ${item.path}: ${error.message || error}`);
    }
  }

  return { uploadedAt, records };
}

function attachUploadCommit(records, uploadCommit) {
  for (const record of records) {
    if (!record.metadata.source) {
      record.metadata.source = {};
    }

    record.metadata.source.upload_commit = uploadCommit;
  }
}

function logPlan({ script, root, items, component, force }) {
  info(script, `vault: ${root}`);
  info(script, force ? 'selection: all matching files (--force)' : 'selection: dirty matching files');
  info(script, `matched ${component.label}: ${items.length}`);

  for (const item of items) {
    info(script, `  ${item.recordType.padEnd(11)} ${item.slug}  ${item.path}`);
  }
}

function runUploadControlComponent(config = {}) {
  const componentName = config.componentName;
  const component = COMPONENTS[componentName];
  const script = config.script || `upload-${componentName}`;
  const defaults = config.defaults || DEFAULTS;

  if (!component) fail(script, `unknown control component: ${componentName}`);

  const options = parseArgs(process.argv.slice(2), script, component);

  if (componentName === 'plans') {
    runUploadPlansFromStore({ script, options });
    return;
  }

  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const items = discoverComponentItems({
    root,
    script,
    componentName,
    force: options.force,
  });

  logPlan({ script, root, items, component, force: options.force });

  if (items.length === 0) {
    info(script, options.force
      ? `no ${component.label} found matching configured prefixes`
      : `no dirty ${component.label} found matching configured prefixes`);
    return;
  }

  if (options.dryRun) {
    info(script, 'dry run: no commit made and no NDJSON emitted');
    return;
  }

  const { records } = prepareUploadRecords({
    root,
    items,
    script,
    component,
    force: options.force,
  });

  if (records.length === 0) {
    info(script, `no valid ${component.label} to upload after skipping errors`);
    process.exitCode = 1;
    return;
  }

  if (records.length !== items.length) {
    info(script, `skipped ${items.length - records.length} invalid ${component.label}; uploading ${records.length}`);
  }

  const uploadCommit = commitComponentFiles({
    root,
    items: records.map((record) => record.item),
    component,
    force: options.force,
  });

  attachUploadCommit(records, uploadCommit);
  info(script, `committed ${component.label} upload custody: ${uploadCommit}`);

  let emitted = 0;
  let failed = 0;

  for (const record of records) {
    try {
      runPandocUpload({
        cwd: root,
        input: record.item.path,
        defaults,
        metadata: record.metadata,
      });
      emitted += 1;
    } catch (error) {
      failed += 1;
      info(script, `ERROR: ${record.item.path}: ${error.message || error}`);
    }
  }

  if (failed > 0) {
    info(script, `uploaded ${emitted} ${component.label}; ${failed} failed`);
    if (emitted === 0) {
      process.exitCode = 1;
    }
  }
}

module.exports = {
  COMPONENTS,
  runUploadControlComponent,
  contentSha256,
  extractDriverConfigFromMarkdown,
  buildComponentUploadMetadata,
  prepareUploadRecords,
  hydrateControlPath,
  discoverComponentItems,
};
