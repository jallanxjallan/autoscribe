'use strict';

const {
  git,
  gitText,
  getGitRoot,
} = require('../../lib/git');

const {
  CliError,
  fail,
  findManagedVaultRoot,
} = require('../../lib/vault-utils');

function usage() {
  console.error('Usage: push-vault [path]');
  console.error('Pushes committed changes from the managed vault repo to its configured upstream.');
  console.error('Dirty/uncommitted files are reported but not pushed.');
}

function parseArgs(argv) {
  let startInput = '.';
  let seenTarget = false;

  for (const arg of argv) {
    if (arg === '-h' || arg === '--help') {
      usage();
      process.exit(0);
    }

    if (arg.startsWith('-')) {
      usage();
      fail(`unknown option: ${arg}`, 64);
    }

    if (seenTarget) {
      usage();
      fail('push-vault accepts at most one path argument.', 64);
    }

    startInput = arg;
    seenTarget = true;
  }

  return { startInput };
}

function gitTextOptional(args, options = {}) {
  const result = git(args, {
    ...options,
    check: false,
  });

  if (result.status !== 0) return '';

  return String(result.stdout || '').trim();
}

function countDirtyFiles(repoRoot) {
  const status = gitText(['status', '--porcelain'], {
    cwd: repoRoot,
  });

  if (!status) return 0;

  return status
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
    .length;
}

function currentBranch(repoRoot) {
  const branch = gitText(['branch', '--show-current'], {
    cwd: repoRoot,
  });

  if (!branch) {
    fail(`refusing to push detached HEAD: ${repoRoot}`);
  }

  return branch;
}

function configuredRemote(repoRoot, branchName) {
  const remoteName = gitTextOptional(['config', `branch.${branchName}.remote`], {
    cwd: repoRoot,
  });

  if (!remoteName) {
    fail(
      `current branch has no configured remote:\n` +
      `       vault:  ${repoRoot}\n` +
      `       branch: ${branchName}\n` +
      `       hint:   create-vault should configure this, or run git push -u <remote> ${branchName}`
    );
  }

  const remoteUrl = gitTextOptional(['remote', 'get-url', remoteName], {
    cwd: repoRoot,
  });

  if (!remoteUrl) {
    fail(
      `configured remote does not exist:\n` +
      `       vault:  ${repoRoot}\n` +
      `       branch: ${branchName}\n` +
      `       remote: ${remoteName}`
    );
  }

  return { remoteName, remoteUrl };
}

function configuredMergeRef(repoRoot, branchName) {
  const mergeRef = gitTextOptional(['config', `branch.${branchName}.merge`], {
    cwd: repoRoot,
  });

  if (!mergeRef) {
    fail(
      `current branch has no configured upstream merge ref:\n` +
      `       vault:  ${repoRoot}\n` +
      `       branch: ${branchName}`
    );
  }

  if (!mergeRef.startsWith('refs/heads/')) {
    fail(
      `unsupported upstream merge ref:\n` +
      `       vault: ${repoRoot}\n` +
      `       ref:   ${mergeRef}`
    );
  }

  return mergeRef;
}

function configuredUpstream(repoRoot) {
  const upstream = gitTextOptional(
    ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'],
    { cwd: repoRoot }
  );

  if (!upstream) {
    fail(
      `current branch has no usable upstream:\n` +
      `       vault: ${repoRoot}\n` +
      `       hint:  create-vault should configure this, or run git push -u <remote> <branch>`
    );
  }

  return upstream;
}

function countCommitsToPush(repoRoot) {
  const countText = gitTextOptional(['rev-list', '--count', '@{u}..HEAD'], {
    cwd: repoRoot,
  });

  if (!countText) return 0;

  const count = Number.parseInt(countText, 10);
  if (Number.isNaN(count)) {
    fail(`could not determine commits to push for vault: ${repoRoot}`);
  }

  return count;
}

function ensureValidVaultRepo(startInput) {
  const vaultRoot = findManagedVaultRoot(startInput);
  const gitRoot = getGitRoot(vaultRoot);

  if (gitRoot !== vaultRoot) {
    fail(
      `managed vault root is not the git repository root:\n` +
      `       vault: ${vaultRoot}\n` +
      `       git:   ${gitRoot}`
    );
  }

  return vaultRoot;
}

function emitGitOutput(result) {
  const stdout = String(result.stdout || '').trim();
  const stderr = String(result.stderr || '').trim();

  if (stdout) console.error(stdout);
  if (stderr) console.error(stderr);
}

function push(repoRoot, remoteName, mergeRef) {
  return git(['push', '-u', remoteName, `HEAD:${mergeRef}`], {
    cwd: repoRoot,
    check: false,
  });
}

function main(argv = process.argv.slice(2)) {
  const { startInput } = parseArgs(argv);

  const vaultRoot = ensureValidVaultRepo(startInput);
  const branchName = currentBranch(vaultRoot);
  const upstream = configuredUpstream(vaultRoot);
  const mergeRef = configuredMergeRef(vaultRoot, branchName);
  const { remoteName, remoteUrl } = configuredRemote(vaultRoot, branchName);

  const dirtyCount = countDirtyFiles(vaultRoot);
  const commitsToPush = countCommitsToPush(vaultRoot);

  console.error(`push-vault: vault: ${vaultRoot}`);
  console.error(`push-vault: branch: ${branchName}`);
  console.error(`push-vault: upstream: ${upstream}`);
  console.error(`push-vault: target: ${remoteName} -> ${remoteUrl}`);
  console.error(`push-vault: ref: HEAD -> ${mergeRef}`);

  if (dirtyCount > 0) {
    console.error(`push-vault: notice: ${dirtyCount} dirty/uncommitted file(s) will not be pushed`);
  }

  if (commitsToPush === 0) {
    console.error('push-vault: notice: no commits to push');
    return;
  }

  console.error(`push-vault: pushing ${commitsToPush} commit(s)`);

  const result = push(vaultRoot, remoteName, mergeRef);

  emitGitOutput(result);

  if (result.status !== 0) {
    console.error(`push-vault: FAILED: git push exited with status ${result.status}`);
    process.exit(result.status || 1);
  }

  console.error(`push-vault: OK: pushed ${commitsToPush} commit(s) to ${remoteName}`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    if (error instanceof CliError) {
      console.error(`push-vault: FAILED: ${error.message}`);
      process.exit(error.exitCode || 1);
    }

    throw error;
  }
}

module.exports = { main };