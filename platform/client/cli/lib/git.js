const { runCommandSync } = require("./shell");

function git(args = [], options = {}) {
  const gitBin = process.env.OBSIDIAN_GIT_BIN || process.env._OBSIDIAN_GIT_BIN || "git";
  return runCommandSync(gitBin, args, {
    cwd: options.cwd,
    input: options.input,
    check: options.check ?? true,
    maxBuffer: options.maxBuffer ?? 20 * 1024 * 1024,
  });
}

function gitText(args = [], options = {}) {
  return String(git(args, options).stdout || "").trim();
}

function getGitRoot(cwd = process.cwd()) {
  return gitText(["rev-parse", "--show-toplevel"], { cwd });
}

function getHeadCommit(cwd = process.cwd()) {
  return gitText(["rev-parse", "HEAD"], { cwd });
}

function isTracked({ root, path }) {
  if (!root) throw new Error("isTracked requires root.");
  if (!path) throw new Error("isTracked requires path.");

  const result = git(["ls-files", "--error-unmatch", "--", path], {
    cwd: root,
    check: false,
  });

  return result.status === 0;
}

function lastCommitForPath({ root, path }) {
  if (!root) throw new Error("lastCommitForPath requires root.");
  if (!path) throw new Error("lastCommitForPath requires path.");

  const result = git(["log", "--max-count=1", "--format=%H", "--", path], {
    cwd: root,
    check: false,
  });

  if (result.status !== 0) return "";
  return String(result.stdout || "").trim();
}

function hasEverBeenCommitted({ root, path }) {
  return lastCommitForPath({ root, path }) !== "";
}

function listDirtyTrackedFiles({ root, pathspecs = [] } = {}) {
  if (!root) throw new Error("listDirtyTrackedFiles requires root.");

  const args = [
    "diff",
    "--name-only",
    "--diff-filter=ACMRTUXB",
    "HEAD",
  ];

  if (Array.isArray(pathspecs) && pathspecs.length > 0) {
    args.push("--", ...pathspecs);
  }

  return String(git(args, { cwd: root }).stdout || "")
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

function listDirtyFiles({ root } = {}) {
  if (!root) throw new Error("listDirtyFiles requires root.");

  const output = String(git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], {
    cwd: root,
  }).stdout || "");

  const entries = output.split("\0").filter(Boolean);
  const paths = [];

  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const status = entry.slice(0, 2);
    const rest = entry.slice(3);

    if (status.includes("R") || status.includes("C")) {
      const newPath = rest.trim();
      if (newPath) paths.push(newPath);
      index += 1;
      continue;
    }

    const relPath = rest.trim();
    if (relPath) paths.push(relPath);
  }

  return [...new Set(paths)].sort((a, b) => a.localeCompare(b));
}

function stageFiles({ root, paths }) {
  if (!root) throw new Error("stageFiles requires root.");
  if (!Array.isArray(paths) || paths.length === 0) return;

  git(["add", "--", ...paths], { cwd: root });
}

function commitFiles({ root, paths, message, body = "", allowEmpty = false }) {
  if (!root) throw new Error("commitFiles requires root.");
  if (!Array.isArray(paths) || paths.length === 0) {
    throw new Error("commitFiles requires at least one path.");
  }
  if (!message) throw new Error("commitFiles requires message.");

  stageFiles({ root, paths });

  const args = ["commit", "--only"];

  if (allowEmpty) {
    args.push("--allow-empty");
  }

  args.push("-m", message);

  if (body) {
    args.push("-m", body);
  }

  args.push("--", ...paths);

  git(args, { cwd: root });
  return getHeadCommit(root);
}

module.exports = {
  git,
  gitText,
  getGitRoot,
  getHeadCommit,
  isTracked,
  lastCommitForPath,
  hasEverBeenCommitted,
  listDirtyTrackedFiles,
  listDirtyFiles,
  stageFiles,
  commitFiles,
};
