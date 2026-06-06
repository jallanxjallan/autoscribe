'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  absPath,
  exists,
  fail,
  warn,
  isDirectory,
  ensureDir,
  readRequiredEnv,
} = require('./common');

const {
  git,
  gitText,
} = require('../../lib/git');

const { openVaultFromCreate } = require('../obsidian/obsidian-open');

const VAULT_REMOTE_NAME =
  process.env._OBSIDIAN_VAULT_REMOTE_NAME ||
  process.env._OBSIDIAN_STUDIO_REMOTE_NAME ||
  'origin';

const DROPBOX_BARE_ROOT =
  process.env._OBSIDIAN_DROPBOX_BARE_ROOT ||
  path.join(os.homedir(), 'Dropbox', 'git', 'obsidian-vaults');

const VAULT_BRANCH =
  process.env._OBSIDIAN_VAULT_BRANCH ||
  'main';

const BARE_REPO_SUFFIX =
  process.env._OBSIDIAN_BARE_REPO_SUFFIX ||
  '.git';

function usage() {
  console.error('Usage: create-vault [--open|--no-open] [path]');
  console.error('Copies the core .obsidian folder into the target directory and initializes vault git.');
  console.error('');
  console.error('Git remote: creates/uses a bare repo in Dropbox.');
  console.error(`Default bare repo root: ${DROPBOX_BARE_ROOT}`);
}

function expandHome(input) {
  if (!input) return input;
  if (input === '~') return os.homedir();
  if (input.startsWith('~/')) return path.join(os.homedir(), input.slice(2));
  return input;
}

function gitBranchSafeFolderName(folderName) {
  const cleaned = folderName
    .trim()
    .replace(/\\/g, '-')
    .replace(/\s+/g, '-')
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[.-]+|[.-]+$/g, '');

  if (!cleaned) fail(`could not derive git-safe name from folder: ${folderName}`);
  return cleaned;
}

function vaultBranchName() {
  git(['check-ref-format', '--branch', VAULT_BRANCH]);
  return VAULT_BRANCH;
}

function bareRepoName(target) {
  return `${gitBranchSafeFolderName(path.basename(target))}${BARE_REPO_SUFFIX}`;
}

function dropboxBareRepoPath(target) {
  return path.join(absPath(expandHome(DROPBOX_BARE_ROOT)), bareRepoName(target));
}

function parseArgs(argv) {
  let openObsidian = true;
  let targetInput = '.';
  let seenTarget = false;

  for (const arg of argv) {
    if (arg === '-h' || arg === '--help') {
      usage();
      process.exit(0);
    }

    if (arg === '--open') {
      openObsidian = true;
      continue;
    }

    if (arg === '--no-open') {
      openObsidian = false;
      continue;
    }

    if (arg.startsWith('-')) {
      usage();
      fail(`unknown option: ${arg}`, 64);
    }

    if (seenTarget) {
      usage();
      fail('create-vault accepts at most one path argument.', 64);
    }

    targetInput = arg;
    seenTarget = true;
  }

  return { openObsidian, targetInput };
}

function copyDirectoryStrict(src, dest) {
  if (!isDirectory(src)) {
    fail(`source directory is missing: ${src}`);
  }

  if (exists(dest)) {
    fail(`destination already exists: ${dest}`);
  }

  fs.cpSync(src, dest, {
    recursive: true,
    force: false,
    errorOnExist: true,
    dereference: false,
    preserveTimestamps: true,
  });
}

function ensureControlSymlink(target, controlRoot) {
  const linkPath = path.join(target, '_control');

  if (exists(linkPath)) {
    fail(`_control already exists: ${linkPath}`);
  }

  fs.symlinkSync(controlRoot, linkPath, 'dir');
}

function ensureGitignoreLine(gitignorePath, line) {
  let text = '';

  if (exists(gitignorePath)) {
    text = fs.readFileSync(gitignorePath, 'utf8');
  }

  const lines = text.split(/\r?\n/);
  if (lines.includes(line)) return;

  if (text.length > 0 && !text.endsWith('\n')) text += '\n';
  text += `${line}\n`;

  fs.writeFileSync(gitignorePath, text, 'utf8');
}

function isBareGitRepo(repoPath) {
  const result = git(['rev-parse', '--is-bare-repository'], {
    cwd: repoPath,
    check: false,
  });

  return result.status === 0 && String(result.stdout || '').trim() === 'true';
}

function ensureBareRemoteRepo(repoPath) {
  const parent = path.dirname(repoPath);
  ensureDir(parent);

  if (exists(repoPath)) {
    if (!isDirectory(repoPath)) {
      fail(`bare remote path exists and is not a directory: ${repoPath}`);
    }

    if (isBareGitRepo(repoPath)) return;

    const entries = fs.readdirSync(repoPath);
    if (entries.length > 0) {
      fail(`remote path exists but is not an empty directory or bare git repo: ${repoPath}`);
    }
  }

  git(['init', '--bare', repoPath], {
    cwd: parent,
  });
}

function configureBareRemote(target, branchName, remoteRepoPath) {
  git(['check-ref-format', '--branch', branchName], {
    cwd: target,
  });

  ensureBareRemoteRepo(remoteRepoPath);

  git(['branch', '-M', branchName], {
    cwd: target,
  });

  const remoteCheck = git(['remote', 'get-url', VAULT_REMOTE_NAME], {
    cwd: target,
    check: false,
  });

  if (remoteCheck.status === 0) {
    git(['remote', 'set-url', VAULT_REMOTE_NAME, remoteRepoPath], {
      cwd: target,
    });
  } else {
    git(['remote', 'add', VAULT_REMOTE_NAME, remoteRepoPath], {
      cwd: target,
    });
  }

  git(['config', `branch.${branchName}.remote`, VAULT_REMOTE_NAME], {
    cwd: target,
  });

  git(['config', `branch.${branchName}.merge`, `refs/heads/${branchName}`], {
    cwd: target,
  });
}

function pushInitialCommit(target, branchName) {
  git(['push', '-u', VAULT_REMOTE_NAME, branchName], {
    cwd: target,
  });
}

function initializeGit(target, branchName, remoteRepoPath) {
  git(['init'], {
    cwd: target,
  });

  configureBareRemote(target, branchName, remoteRepoPath);

  git(['add', '-A'], {
    cwd: target,
  });

  const diff = git(['diff', '--cached', '--quiet'], {
    cwd: target,
    check: false,
  });

  if (diff.status === 0) return;

  if (diff.status !== 1) {
    fail(`git diff failed while initializing vault: ${target}`);
  }

  git(['commit', '-m', 'SNAPSHOT: initialize Obsidian vault from core'], {
    cwd: target,
  });

  const head = gitText(['rev-parse', '--short', 'HEAD'], {
    cwd: target,
  });

  pushInitialCommit(target, branchName);

  console.log(`git commit: ${head}`);
}

function main(argv = process.argv.slice(2)) {
  const { openObsidian, targetInput } = parseArgs(argv);

  const target = absPath(targetInput);
  const coreRoot = readRequiredEnv('OBSIDIAN_CORE_ROOT', '_OBSIDIAN_CORE_ROOT');
  const controlRoot = readRequiredEnv('OBSIDIAN_CONTROL_ROOT', '_OBSIDIAN_CONTROL_ROOT');

  const sourceObsidian = path.join(coreRoot, '.obsidian');
  const targetObsidian = path.join(target, '.obsidian');

  if (!isDirectory(sourceObsidian)) {
    fail(`core .obsidian directory is missing: ${sourceObsidian}`);
  }

  if (!isDirectory(controlRoot)) {
    fail(`control directory is missing: ${controlRoot}`);
  }

  let createdTarget = false;

  if (exists(target)) {
    if (!isDirectory(target)) {
      fail(`target exists and is not a directory: ${target}`);
    }
  } else {
    ensureDir(target);
    createdTarget = true;
  }

  if (exists(targetObsidian)) {
    console.log(`exists: Obsidian vault already exists: ${target}`);
    return;
  }

  try {
    copyDirectoryStrict(sourceObsidian, targetObsidian);
    ensureControlSymlink(target, controlRoot);

    const gitignorePath = path.join(target, '.gitignore');
    ensureGitignoreLine(gitignorePath, '');
    ensureGitignoreLine(gitignorePath, '# Local symlink mount points');
    ensureGitignoreLine(gitignorePath, '# Targets are versioned in their own repositories.');
    ensureGitignoreLine(gitignorePath, '/_control');

    const branchName = vaultBranchName(target);
    const remoteRepoPath = dropboxBareRepoPath(target);

    initializeGit(target, branchName, remoteRepoPath);

    console.log(`${createdTarget ? 'created' : 'initialized'}: ${target}`);
    console.log(`git bare remote: ${VAULT_REMOTE_NAME} -> ${remoteRepoPath}`);
    console.log(`git branch: ${branchName}`);

    if (openObsidian && !openVaultFromCreate(target)) {
      warn('vault was created, but Obsidian was not opened automatically.');
    }
  } catch (error) {
    if (createdTarget) {
      try {
        fs.rmSync(target, { recursive: true, force: true });
      } catch (cleanupError) {
        warn(`cleanup failed for ${target}: ${cleanupError.message}`);
      }
    }

    throw error;
  }
}

module.exports = {
  main,
  vaultBranchName,
  dropboxBareRepoPath,
  gitBranchSafeFolderName,

  // Compatibility alias for older imports/tests.
  studioBranchName: vaultBranchName,
};

if (require.main === module) {
  main();
}