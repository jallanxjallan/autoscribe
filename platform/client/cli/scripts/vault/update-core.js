'use strict';

const { fail, readRequiredEnvPath, isDirectory, findManagedVaultRoot, shellQuote } = require('./common');

const { syncJsonPaths, listCoreJsonPaths } = require('../../lib/core-json');
const { gitDirtyGuard } = require('../../lib/vault-utils');

function usage() {
  console.error('Usage: update-core [--apply] [--dry-run] [--list] [path]');
  console.error('Copies whitelisted JSON files from a managed vault back into the core template.');
  console.error('Default mode is dry-run; pass --apply to copy.');
}

function parseArgs(argv) {
  let apply = false;
  let listOnly = false;
  let startInput = '.';
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
      fail('update-core accepts at most one path argument.', 64);
    }

    startInput = arg;
    seenTarget = true;
  }

  return { apply, listOnly, startInput };
}

function main(argv = process.argv.slice(2)) {
  const { apply, listOnly, startInput } = parseArgs(argv);

  if (listOnly) {
    console.log('Core JSON paths:');
    for (const rel of listCoreJsonPaths()) console.log(`  ${rel}`);
    return;
  }

  const vaultRoot = findManagedVaultRoot(startInput);
  const coreRoot = readRequiredEnvPath('OBSIDIAN_CORE_ROOT', '_OBSIDIAN_CORE_ROOT');

  if (!isDirectory(coreRoot)) {
    fail(`core directory does not exist:\n       ${coreRoot}`);
  }

  if (apply) {
    gitDirtyGuard(coreRoot, 'core template repository');
  }

  console.log('update-core: managed vault JSON -> core');

  const ok = syncJsonPaths({
    sourceRoot: vaultRoot,
    destRoot: coreRoot,
    apply,
    sourceLabel: 'vault',
    destLabel: 'core',
  });

  if (!ok) process.exit(1);

  if (!apply) {
    console.log('run with --apply to copy managed vault JSON back into core');
    return;
  }

  console.log('');
  console.log('Review core changes with:');
  console.log(`  git -C ${shellQuote(coreRoot)} status --short`);
  console.log(`  git -C ${shellQuote(coreRoot)} diff -- .obsidian`);
}

module.exports = { main };

if (require.main === module) main();
