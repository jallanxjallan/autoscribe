const { getVaultRoot, assertVaultRoot, gatherVaultSlugs } = require("./vault");
const { listPendingExports } = require("./asc");
const { writeWritingManifest } = require("./manifest");

const DEFAULT_ASC_BIN = process.env._AUTOSCRIBE_ASC_BIN || process.env.ASC_BIN || "asc";

function fail(script, message, code = 1) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(code);
}

function info(script, message) {
  console.error(`${script}: ${message}`);
}

function usage(config) {
  if (config.mode === "writeback") {
    console.error(`Usage:
  writeback [--dry-run] [--limit N] [--asc-bin BIN]

Behavior:
  Finds pending exports whose prompt_slug already exists in the active vault,
  extracts each result with asc export extract-result <call_identity>, replaces
  only the target Markdown body, preserves target frontmatter, marks the result
  exported with asc export update-exports <result_identity>, and saves a
  writeback manifest.

Safety:
  - aborts on duplicate vault slugs
  - aborts if two pending results target the same vault slug
  - aborts before export if any target file is dirty
  - rechecks each target immediately before writing
  - leaves changed files dirty for human review

Options:
  -n, --dry-run       Show matching candidates; do not extract, write, or mark.
  --limit N           Process at most N matching results after preflight.
  --asc-bin BIN       AutoScribe executable. Default: ${DEFAULT_ASC_BIN}
  -h, --help          Show this help.
`);
    return;
  }

  console.error(`Usage:
  writenew [target-dir] [--dry-run] [--limit N] [--asc-bin BIN]

Behavior:
  Finds pending exports with provisional prv.* prompt slugs, extracts each result
  with asc export extract-result <call_identity>, writes new Markdown files under
  target-dir, marks each result exported with asc export update-exports
  <result_identity>, and saves a writenew manifest.

Options:
  target-dir          Vault-relative output directory. Default: ${config.defaultTargetDir || "new"}
  -n, --dry-run       Show matching candidates; do not write or mark.
  --limit N           Process at most N matching results.
  --asc-bin BIN       AutoScribe executable. Default: ${DEFAULT_ASC_BIN}
  -h, --help          Show this help.
`);
}

function parseArgs(argv, config) {
  const options = {
    dryRun: false,
    limit: null,
    ascBin: DEFAULT_ASC_BIN,
    targetDirArg: config.defaultTargetDir,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === "--dry-run" || arg === "-n") {
      options.dryRun = true;
    } else if (arg === "--limit") {
      const value = Number(argv[++i]);
      if (!Number.isInteger(value) || value < 1) {
        fail(config.script, "--limit requires a positive integer", 64);
      }
      options.limit = value;
    } else if (arg.startsWith("--limit=")) {
      const value = Number(arg.slice("--limit=".length));
      if (!Number.isInteger(value) || value < 1) {
        fail(config.script, "--limit requires a positive integer", 64);
      }
      options.limit = value;
    } else if (arg === "--asc-bin") {
      options.ascBin = argv[++i] || "";
      if (!options.ascBin) fail(config.script, "--asc-bin requires a command", 64);
    } else if (arg.startsWith("--asc-bin=")) {
      options.ascBin = arg.slice("--asc-bin=".length);
      if (!options.ascBin) fail(config.script, "--asc-bin requires a command", 64);
    } else if (arg === "--help" || arg === "-h") {
      usage(config);
      process.exit(0);
    } else if (!arg.startsWith("-") && config.mode === "writenew") {
      options.targetDirArg = arg;
    } else {
      fail(config.script, `unknown argument: ${arg}`, 64);
    }
  }

  return options;
}

function normalizePreparedResult(result, selected) {
  if (Array.isArray(result)) {
    return {
      items: result,
      targetDir: selected.targetDir || null,
      summaryLines: [],
    };
  }

  return {
    items: result.items || [],
    targetDir: result.targetDir || selected.targetDir || null,
    summaryLines: result.summaryLines || [],
  };
}

function printCandidate(script, item) {
  const identityPart = item.callIdentity && item.resultIdentity
    ? `call ${item.callIdentity}  result ${item.resultIdentity}  `
    : "";
  const hintPart = item.filenameHint ? `  hint ${item.filenameHint}` : "";
  info(script, `candidate: ${identityPart}${item.promptSlug} -> ${item.path}${hintPart}`);
}

function runWritingCommand(config) {
  const options = parseArgs(process.argv.slice(2), config);
  const root = getVaultRoot(process.cwd());

  assertVaultRoot({ root, script: config.script });

  info(config.script, `vault: ${root}`);

  const vaultSlugs = gatherVaultSlugs({ root, script: config.script });
  info(config.script, `vault slugs: ${vaultSlugs.size}`);

  const pendingExports = listPendingExports({
    root,
    ascBin: options.ascBin,
    script: config.script,
  });
  info(config.script, `pending exports: ${pendingExports.length}`);

  if (pendingExports.length === 0) {
    console.log(`${config.script}: no pending exports`);
    return;
  }

  let selected = config.selectCandidates({
    root,
    vaultSlugs,
    pendingExports,
    options,
    script: config.script,
  });

  if (options.limit !== null) {
    selected = {
      ...selected,
      items: selected.items.slice(0, options.limit),
    };
  }

  for (const line of selected.summaryLines || []) {
    info(config.script, line);
  }

  if (selected.items.length === 0) {
    console.log(`${config.script}: no matching pending exports`);
    return;
  }

  let prepared = {
    items: selected.items,
    targetDir: selected.targetDir || null,
    summaryLines: [],
  };

  if (config.prepareItems) {
    prepared = normalizePreparedResult(config.prepareItems({
      root,
      items: selected.items,
      options,
      script: config.script,
    }), selected);
  }

  for (const line of prepared.summaryLines || []) {
    info(config.script, line);
  }

  for (const item of prepared.items) {
    printCandidate(config.script, item);
  }

  if (options.dryRun) {
    console.log(`${config.script}: dry run; ${prepared.items.length} candidate(s), no files changed or marked exported`);
    return;
  }

  const written = [];

  for (const item of prepared.items) {
    written.push(config.applyItem({
      root,
      item,
      options,
      script: config.script,
    }));
  }

  writeWritingManifest({
    root,
    mode: config.mode,
    targetDir: prepared.targetDir,
    written,
    script: config.script,
  });

  const changed = written.filter(item => item.changed).length;
  const unchanged = written.length - changed;

  if (config.mode === "writeback") {
    console.log(`writeback: wrote ${changed} file(s); ${unchanged} unchanged; marked ${written.length} export(s); review dirty files before committing`);
  } else {
    console.log(`writenew: wrote ${written.length} new file(s); marked ${written.length} export(s)`);
  }
}

module.exports = {
  runWritingCommand,
};
