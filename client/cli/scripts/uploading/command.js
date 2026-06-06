'use strict';

function fail(script, message) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(1);
}

function info(script, message) {
  console.error(`${script}: ${message}`);
}

function parseManifestCommandArgs({ argv, script, defaultMaxAgeSeconds, usage }) {
  const options = {
    dryRun: false,
    manifestPath: '',
    allowStaleManifest: false,
    maxAgeSeconds: defaultMaxAgeSeconds,
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
    } else if (arg === '--allow-stale-manifest') {
      options.allowStaleManifest = true;
    } else if (arg === '--max-age-seconds') {
      const value = Number(argv[++i]);
      if (!Number.isFinite(value) || value < 0) {
        fail(script, '--max-age-seconds requires a non-negative number');
      }
      options.maxAgeSeconds = value;
    } else if (arg.startsWith('--max-age-seconds=')) {
      const value = Number(arg.slice('--max-age-seconds='.length));
      if (!Number.isFinite(value) || value < 0) {
        fail(script, '--max-age-seconds requires a non-negative number');
      }
      options.maxAgeSeconds = value;
    } else if (arg === '--help' || arg === '-h') {
      usage(script);
      process.exit(0);
    } else {
      fail(script, `unknown argument: ${arg}`);
    }
  }

  return options;
}

module.exports = {
  fail,
  info,
  parseManifestCommandArgs,
};
