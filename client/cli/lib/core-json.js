'use strict';

const fs = require('fs');
const path = require('path');
const { isRegularFile } = require('./vault-utils');

const CORE_JSON_PATHS = Object.freeze([
  '.obsidian/hotkeys.json',
  '.obsidian/core-plugins.json',
  '.obsidian/community-plugins.json',
  '.obsidian/appearance.json',
  '.obsidian/templates.json',

  '.obsidian/plugins/quickadd/data.json',
  '.obsidian/plugins/templater/data.json',
  '.obsidian/plugins/dataview/data.json',
]);

function validateRelativePath(rel) {
  if (path.isAbsolute(rel)) {
    throw new Error(`core JSON path must be relative: ${rel}`);
  }

  const normalized = path.normalize(rel);
  if (normalized === '..' || normalized.startsWith(`..${path.sep}`)) {
    throw new Error(`core JSON path may not escape root: ${rel}`);
  }

  if (normalized !== rel) {
    throw new Error(`core JSON path is not normalized: ${rel}`);
  }
}

function sameFileContent(a, b) {
  if (!isRegularFile(a) || !isRegularFile(b)) return false;
  return fs.readFileSync(a).equals(fs.readFileSync(b));
}

function copyJsonFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  fs.chmodSync(dest, fs.statSync(src).mode);
}

function listCoreJsonPaths() {
  CORE_JSON_PATHS.forEach(validateRelativePath);
  return [...CORE_JSON_PATHS];
}

function syncJsonPaths({ sourceRoot, destRoot, apply, sourceLabel, destLabel }) {
  let changed = 0;
  let unchanged = 0;
  let missing = 0;
  let errors = 0;
  let copied = 0;

  console.log(`source: ${sourceLabel}`);
  console.log(`        ${sourceRoot}`);
  console.log(`target: ${destLabel}`);
  console.log(`        ${destRoot}`);

  for (const rel of listCoreJsonPaths()) {
    const src = path.join(sourceRoot, rel);
    const dest = path.join(destRoot, rel);

    if (!isRegularFile(src)) {
      console.error(`WARN: source JSON missing, skipping: ${rel}`);
      missing += 1;
      continue;
    }

    if (fs.existsSync(dest)) {
      if (!isRegularFile(dest)) {
        console.error('ERROR: destination exists but is not a regular JSON file:');
        console.error(`       ${dest}`);
        errors += 1;
        continue;
      }

      if (sameFileContent(src, dest)) {
        console.log(`unchanged: ${rel}`);
        unchanged += 1;
        continue;
      }
    }

    changed += 1;

    if (!apply) {
      console.log(`${fs.existsSync(dest) ? 'would update' : 'would create'}: ${rel}`);
      continue;
    }

    try {
      copyJsonFile(src, dest);
      console.log(`updated: ${rel}`);
      copied += 1;
    } catch (error) {
      console.error('ERROR: failed to copy JSON:');
      console.error(`       from: ${src}`);
      console.error(`       to:   ${dest}`);
      console.error(`       ${error.message}`);
      errors += 1;
    }
  }

  if (apply) {
    console.log(`summary: copied=${copied} changed=${changed} unchanged=${unchanged} missing=${missing} errors=${errors}`);
  } else {
    console.log(`summary: would_change=${changed} unchanged=${unchanged} missing=${missing} errors=${errors}`);
  }

  return errors === 0;
}

module.exports = {
  CORE_JSON_PATHS,
  listCoreJsonPaths,
  syncJsonPaths,
};