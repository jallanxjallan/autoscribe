'use strict';

const { fail, readRequiredEnvPath, isDirectory, findManagedVaultRoot } = require('./common');

const { syncJsonPaths, listCoreJsonPaths } = require('../../lib/core-json');
const { gitDirtyGuard } = require('../../lib/vault-utils');

function usage() {
  console.error('Usage: update-vault [--apply] [--dry-run] [--list] [path]');
  console.error('Copies whitelisted core JSON files into the current or specified managed vault.');
  console.error('Default mode is dry-run; pass --apply to copy.');
}

function parseArgs(argv) {
  let apply = false;
  let listOnly = false;
  let targetInput = '.';
  let seenTarget = false;

  for (const arg of argv) {
    if (arg === '-h' || arg === '--help') {
      usage();
      process.exit(0);
    }

    if (arg === '-y' || arg === '--apply') {
      apply = true;
      continue;
    }

    if (arg === '-n' || arg === '--dry-run') {
      apply = false;
      continue;
    }

    if (arg === '--list') {
      listOnly = true;
      continue;
    }

    if (arg.startsWith('-')) {
      usage();
      fail(`unknown option: ${arg}`, 64);
    }

    if (seenTarget) {
      usage();
      fail('update-vault accepts at most one path argument.', 64);
    }

    targetInput = arg;
    seenTarget = true;
  }

  return { apply, listOnly, targetInput };
}

function main(argv = process.argv.slice(2)) {
  const { apply, listOnly, targetInput } = parseArgs(argv);

  if (listOnly) {
    console.log('Core JSON paths:');
    for (const rel of listCoreJsonPaths()) console.log(`  ${rel}`);
    return;
  }

  const coreRoot = readRequiredEnvPath('OBSIDIAN_CORE_ROOT', '_OBSIDIAN_CORE_ROOT');
  const target = findManagedVaultRoot(targetInput);

  if (!isDirectory(coreRoot)) {
    fail(`core directory does not exist:\n       ${coreRoot}`);
  }

  if (apply) {
    gitDirtyGuard(target, 'managed vault');
  }

  console.log('update-vault: core JSON -> managed vault');

  const ok = syncJsonPaths({
    sourceRoot: coreRoot,
    destRoot: target,
    apply,
    sourceLabel: 'core',
    destLabel: 'vault',
  });

  if (!ok) process.exit(1);

  if (!apply) {
    console.log('run with --apply to copy core JSON into the managed vault');
  }
}

module.exports = { main };

if (require.main === module) main();
