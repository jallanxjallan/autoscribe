'use strict';

const childProcess = require('node:child_process');
const path = require('node:path');

const { fail, info, parseManifestCommandArgs } = require('./command');
const { getManifest, uniqueManifestRows } = require('./manifest');
const { assertVaultRoot } = require('./selection');
const { getGitRoot } = require('../../lib/git');
const { resolveJobControls } = require('../../lib/job-control-resolver');
const { staleLocalControls, markControlsUploaded } = require('../../lib/control-state');
const { preflightManifestComponent } = require('./upload-control-component');

const SCRIPT = 'enqueue-job';
const ENQUEUE_OPERATION = 'enqueue-jobs';
const ENQUEUE_QUERY_NAME = 'Enqueue Jobs';
const CONTROL_OPERATION = 'control-status';
const CONTROL_QUERY_NAME = 'Control Status';
const DEFAULT_MAX_MANIFEST_AGE_SECONDS = 120;

function usage(script) {
  console.error(`Usage:
  ${script} [--dry-run] [--manifest PATH] [--allow-stale-manifest]
          [--max-age-seconds N]

Behavior:
  Reads the saved Enqueue Jobs manifest, finds the referenced job definition,
  resolves the job's local control slugs, checks body/content hashes against
  .locals.autoscribe/control-upload-state.json, and uploads selected local
  controls before enqueueing prompts when local controls are stale.

  Global controls are visible to job definitions but are not checked for
  currency client-side. asc enqueue remains the final verifier.

Options:
  -n, --dry-run              Show what would run; do not upload or enqueue.
  --manifest PATH            Use this Enqueue Jobs manifest instead of the active-vault one.
  --allow-stale-manifest     Disable the Enqueue Jobs manifest freshness guard.
  --max-age-seconds N        Freshness limit for Enqueue Jobs manifest. Default: ${DEFAULT_MAX_MANIFEST_AGE_SECONDS}.
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
    operation: ENQUEUE_OPERATION,
    queryName: ENQUEUE_QUERY_NAME,
  });
}

function getControlManifest({ root, script }) {
  return getManifest({
    options: {
      dryRun: false,
      manifestPath: '',
      allowStaleManifest: true,
      maxAgeSeconds: 0,
    },
    root,
    script,
    operation: CONTROL_OPERATION,
    queryName: CONTROL_QUERY_NAME,
  });
}

function jobSlugFromEnqueueManifest({ manifest, script }) {
  const rows = uniqueManifestRows({
    manifest,
    script,
    queryName: ENQUEUE_QUERY_NAME,
  });

  const slugs = [...new Set(rows.map((row) => row.job_slug).filter(Boolean))];

  if (slugs.length === 0) {
    fail(script, 'Enqueue Jobs manifest contains no job_slug values');
  }

  if (slugs.length > 1) {
    fail(script, `Enqueue Jobs manifest contains multiple job slugs: ${slugs.join(', ')}`);
  }

  return slugs[0];
}

function scriptPath(relativeScript) {
  return path.join(__dirname, `${relativeScript}.js`);
}

function ascCommand() {
  return process.env.ASC_BIN || process.env._AUTOSCRIBE_ASC_BIN || 'asc';
}

function runProducerToAsc({ root, producerScript, producerArgs, ascArgs, label, script }) {
  const producerPath = scriptPath(producerScript);

  const producer = childProcess.spawnSync(process.execPath, [producerPath, ...producerArgs], {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });

  if (producer.stderr) process.stderr.write(producer.stderr);

  if (producer.error) {
    fail(script, `${label} failed to start: ${producer.error.message}`);
  }

  if ((producer.status ?? 0) !== 0) {
    fail(script, `${label} failed with exit status ${producer.status}`);
  }

  const consumer = childProcess.spawnSync(ascCommand(), ascArgs, {
    cwd: root,
    input: producer.stdout || '',
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });

  if (consumer.stdout) process.stdout.write(consumer.stdout);
  if (consumer.stderr) process.stderr.write(consumer.stderr);

  if (consumer.error) {
    fail(script, `asc ${ascArgs.join(' ')} failed to start: ${consumer.error.message}`);
  }

  if ((consumer.status ?? 0) !== 0) {
    fail(script, `asc ${ascArgs.join(' ')} failed with exit status ${consumer.status}`);
  }
}

function selectedControlItemsFromManifest({ root, script }) {
  const manifest = getControlManifest({ root, script });
  const drivers = preflightManifestComponent({ root, manifest, script, componentName: 'drivers', allowEmpty: true });
  const instructions = preflightManifestComponent({ root, manifest, script, componentName: 'instructions', allowEmpty: true });
  return [...drivers, ...instructions].map((item) => ({
    slug: item.slug,
    family: item.recordType,
    type: item.recordType === 'driver' ? 'driver' : '',
    scope: 'vault',
    path: item.path,
    content_sha256: item.content_sha256,
  }));
}

function logStaleControls({ script, stale }) {
  if (!stale.length) return;
  info(script, `stale local controls: ${stale.length}`);
  for (const entry of stale) {
    const control = entry.control;
    info(script, `  ${control.slug}  ${control.path}  (${entry.reason})`);
  }
}

function recheckStale({ root, jobSlug }) {
  const resolved = resolveJobControls({ vaultRoot: root, jobSlug });
  if (resolved.missing.length > 0) {
    return {
      resolved,
      stale: [],
      missing: resolved.missing,
    };
  }

  return {
    resolved,
    stale: staleLocalControls({ vaultRoot: root, controls: resolved.localControls }),
    missing: [],
  };
}

function runEnqueueJob(config = {}) {
  const script = config.script || SCRIPT;
  const options = parseArgs(process.argv.slice(2), script);
  const root = getGitRoot(process.cwd());

  assertVaultRoot({ root, script });

  const enqueueManifest = getEnqueueManifest({ options, root, script });
  const jobSlug = jobSlugFromEnqueueManifest({ manifest: enqueueManifest, script });
  const initial = recheckStale({ root, jobSlug });

  info(script, `vault: ${root}`);
  info(script, `job: ${jobSlug}`);
  info(script, `job definition: ${initial.resolved.job.filepath}`);
  info(script, `resolved controls: ${initial.resolved.resolved.length} (${initial.resolved.localControls.length} local, ${initial.resolved.globalControls.length} global)`);

  if (initial.missing.length > 0) {
    fail(script, `job references controls that were not found locally or globally:\n${initial.missing.map((slug) => `  - ${slug}`).join('\n')}`);
  }

  logStaleControls({ script, stale: initial.stale });

  if (options.dryRun) {
    info(script, 'dry run: no controls uploaded and no prompts enqueued');
    return;
  }

  if (initial.stale.length > 0) {
    const staleFamilies = new Set(initial.stale.map((entry) => entry.control.family));

    if (staleFamilies.has('driver')) {
      info(script, 'uploading selected local drivers before enqueue');

      runProducerToAsc({
        root,
        producerScript: 'upload-drivers',
        producerArgs: ['--allow-stale-manifest'],
        ascArgs: ['control', 'drivers'],
        label: 'upload-drivers',
        script,
      });
    }

    if (staleFamilies.has('instruction')) {
      info(script, 'uploading selected local instructions before enqueue');

      runProducerToAsc({
        root,
        producerScript: 'upload-instructions',
        producerArgs: ['--allow-stale-manifest'],
        ascArgs: ['control', 'instructions'],
        label: 'upload-instructions',
        script,
      });
    }

    const selectedControls = selectedControlItemsFromManifest({ root, script });
    const statePath = markControlsUploaded({ vaultRoot: root, controls: selectedControls });
    info(script, `updated local control upload state: ${statePath}`);

    const afterUpload = recheckStale({ root, jobSlug });
    if (afterUpload.missing.length > 0) {
      fail(script, `job references controls that were not found after upload:\n${afterUpload.missing.map((slug) => `  - ${slug}`).join('\n')}`);
    }
    if (afterUpload.stale.length > 0) {
      logStaleControls({ script, stale: afterUpload.stale });
      fail(script, 'some job-local controls are still stale; update the Control Status selection and run again');
    }
  }

  info(script, 'enqueueing prompts');

  runProducerToAsc({
    root,
    producerScript: 'enqueue-prompts-command',
    producerArgs: process.argv.slice(2),
    ascArgs: ['enqueue', 'prompts'],
    label: 'enqueue-prompts',
    script,
  });
}

module.exports = {
  runEnqueueJob,
};

if (require.main === module) {
  runEnqueueJob();
}
