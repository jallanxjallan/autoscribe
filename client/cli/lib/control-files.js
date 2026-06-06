'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { sha256 } = require('../scripts/uploading/records');
const {
  parseFrontmatterDataFromMarkdown,
  stripFrontmatter,
} = require('./markdown');
const { slugPrefix } = require('./slug');

const CONTROL_PREFIXES = new Set(['drv', 'ins', 'scr', 'script', 'rag']);
const DRIVER_TYPES = new Set(['llm', 'script', 'rag']);
const SKIP_DIRS = new Set([
  '.git',
  '.obsidian',
  '.autoscribe',
  '.locals.autoscribe',
  '_control',
  '_deprecated',
  'node_modules',
]);

function normalizeText(value) {
  return String(value ?? '').trim();
}

function normalizeDriverType(value) {
  const text = normalizeText(value).toLowerCase();
  if (text === 'local') return 'script';
  return DRIVER_TYPES.has(text) ? text : '';
}

function expandHome(value) {
  const text = normalizeText(value);
  if (!text) return '';
  if (text === '~') return os.homedir();
  if (text.startsWith(`~${path.sep}`)) return path.join(os.homedir(), text.slice(2));
  return text;
}

function unique(values) {
  const seen = new Set();
  const result = [];

  for (const value of values || []) {
    const text = normalizeText(value);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }

  return result;
}

function splitPathList(value) {
  return normalizeText(value)
    .split(path.delimiter)
    .map((item) => item.trim())
    .filter(Boolean);
}

function defaultGlobalControlRoots(env = process.env) {
  return unique([
    ...splitPathList(env.OBSIDIAN_GLOBAL_CONTROLS),
    ...splitPathList(env.OBSIDIAN_GLOBAL_CONTROL_ROOT),
    ...splitPathList(env.OBSIDIAN_GLOBAL_INSTRUCTIONS),
    path.join(os.homedir(), 'Workspace', 'Library', 'controls'),
    path.join(os.homedir(), 'Workspace', 'Library'),
    '/Library/controls',
  ].map(expandHome));
}

function existingDirectories(paths) {
  return unique(paths)
    .map(expandHome)
    .filter((candidate) => {
      try {
        return fs.statSync(candidate).isDirectory();
      } catch (_) {
        return false;
      }
    });
}

function markdownContentHash(markdown) {
  return sha256(stripFrontmatter(markdown).trim());
}

function controlKindForSlug(slug, frontmatter = {}) {
  const explicit = normalizeText(frontmatter.type || frontmatter.kind || frontmatter.control_type).toLowerCase();
  if (explicit === 'driver') return 'driver';
  if (explicit === 'instruction') return 'instruction';
  if (explicit === 'script') return 'script';
  if (explicit === 'rag') return 'rag';

  const prefix = slugPrefix(slug);
  if (prefix === 'drv') return 'driver';
  if (prefix === 'ins' || prefix === 'gbl' || prefix === 'cxt' || prefix === 'spc') return 'instruction';
  if (prefix === 'scr' || prefix === 'script') return 'script';
  if (prefix === 'rag') return 'rag';
  return '';
}

function isControlSlug(slug) {
  const prefix = slugPrefix(slug);
  return CONTROL_PREFIXES.has(prefix) || ['gbl', 'cxt', 'spc'].includes(prefix);
}

function controlLabel({ frontmatter, filepath }) {
  return (
    normalizeText(frontmatter.label) ||
    normalizeText(frontmatter.title) ||
    path.basename(filepath, path.extname(filepath))
  );
}

function driverTypeFromFrontmatter(frontmatter = {}) {
  const driver = frontmatter.driver && typeof frontmatter.driver === 'object'
    ? frontmatter.driver
    : {};

  return normalizeDriverType(
    driver['driver-type'] ||
    driver.driver_type ||
    driver.type ||
    frontmatter.driver_type ||
    frontmatter.driverType ||
    frontmatter.engine
  );
}

function normalizeControlFile({ root, filepath, scope }) {
  const markdown = fs.readFileSync(filepath, 'utf8');
  const frontmatter = parseFrontmatterDataFromMarkdown(markdown);
  const slug = normalizeText(frontmatter.slug);

  if (!slug || !isControlSlug(slug)) return null;

  const family = controlKindForSlug(slug, frontmatter);
  if (!family) return null;

  const relPath = path.relative(root, filepath).replace(/\\/g, '/');
  const type = family === 'driver' ? driverTypeFromFrontmatter(frontmatter) : '';

  return {
    ref: slug,
    slug,
    family,
    type,
    label: controlLabel({ frontmatter, filepath }),
    description: normalizeText(frontmatter.description || frontmatter.summary || frontmatter.scope || type),
    scope,
    path: relPath,
    absPath: filepath,
    root,
    source: scope,
    content_sha256: markdownContentHash(markdown),
    raw: {
      frontmatter,
      path: relPath,
      absPath: filepath,
    },
  };
}

function shouldSkipDir(entryName) {
  return SKIP_DIRS.has(entryName) || entryName.startsWith('.trash');
}

function collectMarkdownFiles(root) {
  const files = [];

  function walk(dir) {
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (_) {
      return;
    }

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!shouldSkipDir(entry.name)) walk(fullPath);
        continue;
      }
      if (entry.isFile() && entry.name.toLowerCase().endsWith('.md')) {
        files.push(fullPath);
      }
    }
  }

  walk(root);
  return files;
}

function scanControlRoot({ root, scope }) {
  const resolvedRoot = path.resolve(expandHome(root));

  if (!fs.existsSync(resolvedRoot)) return [];

  return collectMarkdownFiles(resolvedRoot)
    .map((filepath) => normalizeControlFile({ root: resolvedRoot, filepath, scope }))
    .filter(Boolean);
}

function dedupeControls(controls) {
  const byKey = new Map();

  for (const control of controls || []) {
    const key = `${control.scope}:${control.slug}:${control.absPath}`;
    if (!byKey.has(key)) byKey.set(key, control);
  }

  return [...byKey.values()].sort((a, b) => (
    String(a.family).localeCompare(String(b.family), undefined, { sensitivity: 'base' }) ||
    String(a.label).localeCompare(String(b.label), undefined, { sensitivity: 'base' }) ||
    String(a.slug).localeCompare(String(b.slug), undefined, { sensitivity: 'base' })
  ));
}

function listAvailableControls({ vaultRoot, globalRoots = null, env = process.env } = {}) {
  if (!vaultRoot) throw new Error('listAvailableControls requires vaultRoot.');

  const localControls = scanControlRoot({ root: vaultRoot, scope: 'vault' });
  const globalControlRoots = existingDirectories(globalRoots || defaultGlobalControlRoots(env));
  const globalControls = globalControlRoots.flatMap((root) => scanControlRoot({ root, scope: 'global' }));

  return {
    localControls: dedupeControls(localControls),
    globalControls: dedupeControls(globalControls),
    globalControlRoots,
    controls: dedupeControls([...localControls, ...globalControls]),
  };
}

function groupControls(controls = []) {
  const drivers = [];
  const instructionControls = [];
  const scripts = [];
  const rag = [];
  const unknown = [];

  for (const control of controls) {
    if (control.family === 'driver') drivers.push(control);
    else if (control.family === 'instruction') instructionControls.push(control);
    else if (control.family === 'script') scripts.push(control);
    else if (control.family === 'rag') rag.push(control);
    else unknown.push(control);
  }

  return {
    registries: { drivers, scripts, rag },
    drivers,
    instructionControls,
    // Transitional alias: existing job JSON and UI code still use steps[].instructions.
    instructions: instructionControls,
    scripts,
    rag,
    unknown,
    controlsBySlug: Object.fromEntries(controls.map((item) => [item.slug, item])),
  };
}

module.exports = {
  CONTROL_PREFIXES,
  DRIVER_TYPES,
  defaultGlobalControlRoots,
  existingDirectories,
  markdownContentHash,
  normalizeDriverType,
  listAvailableControls,
  scanControlRoot,
  groupControls,
};
