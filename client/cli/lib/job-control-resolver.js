'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { autoscribeHome, getVaultKeyFromRoot } = require('./operation-manifest');
const { listAvailableControls } = require('./control-files');

const CONTROL_SLUG_RE = /\b(?:drv|ins|gbl|cxt|spc|scr|script|rag)\.[A-Za-z0-9][A-Za-z0-9._-]*\b/gu;

function normalizeText(value) {
  return String(value ?? '').trim();
}

function readJsonIfExists(filepath) {
  if (!filepath || !fs.existsSync(filepath)) return null;
  return JSON.parse(fs.readFileSync(filepath, 'utf8'));
}

function jsonFilesInDir(dir) {
  if (!dir || !fs.existsSync(dir)) return [];

  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .filter((entry) => entry.name.toLowerCase().endsWith('.json'))
    .map((entry) => path.join(dir, entry.name));
}

function autoscribeJobDir(vaultRoot) {
  const vaultKey = getVaultKeyFromRoot(vaultRoot);
  return path.join(autoscribeHome(), 'obsidian', 'vaults', vaultKey, 'jobs');
}

function candidateJobFiles({ vaultRoot, jobSlug }) {
  const candidates = [
    ...jsonFilesInDir(autoscribeJobDir(vaultRoot)),
    ...jsonFilesInDir(path.join(vaultRoot, '_jobs')),
  ];

  const slugHint = normalizeText(jobSlug).replace(/[^A-Za-z0-9._-]+/g, '-');
  if (slugHint) {
    candidates.unshift(path.join(autoscribeJobDir(vaultRoot), `${slugHint}.json`));
    candidates.unshift(path.join(vaultRoot, '_jobs', `${slugHint}.json`));
  }

  return [...new Set(candidates)];
}

function loadJobDefinitionForSlug({ vaultRoot, jobSlug }) {
  if (!vaultRoot) throw new Error('loadJobDefinitionForSlug requires vaultRoot.');
  if (!jobSlug) throw new Error('loadJobDefinitionForSlug requires jobSlug.');

  for (const filepath of candidateJobFiles({ vaultRoot, jobSlug })) {
    const payload = readJsonIfExists(filepath);
    if (!payload) continue;

    if (
      payload.slug === jobSlug ||
      payload.job_slug === jobSlug ||
      payload.title === jobSlug ||
      path.basename(filepath, '.json') === jobSlug ||
      path.basename(filepath, '.json').includes(jobSlug)
    ) {
      return { payload, filepath };
    }
  }

  throw new Error(`Could not find job definition for ${jobSlug}. Checked Autoscribe jobs dir and vault _jobs.`);
}

function collectControlSlugs(value, output = new Set()) {
  if (value === null || value === undefined) return output;

  if (typeof value === 'string') {
    for (const match of value.matchAll(CONTROL_SLUG_RE)) {
      output.add(match[0]);
    }
    return output;
  }

  if (Array.isArray(value)) {
    for (const item of value) collectControlSlugs(item, output);
    return output;
  }

  if (typeof value === 'object') {
    for (const item of Object.values(value)) collectControlSlugs(item, output);
  }

  return output;
}

function resolveJobControls({ vaultRoot, jobSlug, globalRoots = null }) {
  const job = loadJobDefinitionForSlug({ vaultRoot, jobSlug });
  const requiredSlugs = [...collectControlSlugs(job.payload)].sort();
  const available = listAvailableControls({ vaultRoot, globalRoots });
  const bySlug = new Map(available.controls.map((control) => [control.slug, control]));

  const resolved = [];
  const missing = [];

  for (const slug of requiredSlugs) {
    const control = bySlug.get(slug);
    if (control) resolved.push(control);
    else missing.push(slug);
  }

  return {
    job,
    requiredSlugs,
    resolved,
    missing,
    localControls: resolved.filter((control) => control.scope === 'vault'),
    globalControls: resolved.filter((control) => control.scope === 'global'),
    available,
  };
}

module.exports = {
  CONTROL_SLUG_RE,
  autoscribeJobDir,
  loadJobDefinitionForSlug,
  collectControlSlugs,
  resolveJobControls,
};
