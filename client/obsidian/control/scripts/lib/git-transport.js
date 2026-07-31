"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runCommandSync } = require("./shell.js");

const RUN_REF_PREFIX = "refs/heads/autoscribe/run/";
const RUN_BRANCH_PREFIX = "autoscribe/run/";
const DISPATCH_MANIFEST = ".autoscribe/dispatch.json";
const RESPONSE_MANIFEST = ".autoscribe/response.json";
const WRITEBACK_MANIFEST = ".autoscribe/writeback.json";

function vaultRoot(app) {
  const root = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!root) throw new Error("Obsidian vault adapter does not expose a filesystem root");
  return path.resolve(root);
}

function git(root, args, options = {}) {
  return runCommandSync("git", ["-C", root, ...args], {
    cwd: root,
    maxBuffer: 64 * 1024 * 1024,
    ...options,
  });
}

function repositoryRoot(app) {
  const root = vaultRoot(app);
  return String(git(root, ["rev-parse", "--show-toplevel"]).stdout || "").trim() || root;
}

function currentBranch(root) {
  return String(git(root, ["branch", "--show-current"]).stdout || "").trim();
}

function headCommit(root) {
  return String(git(root, ["rev-parse", "HEAD"]).stdout || "").trim();
}

function assertRelativePath(root, value) {
  const relative = String(value || "").replace(/\\/g, "/").replace(/^\.\//, "");
  if (!relative || path.isAbsolute(relative) || relative.split("/").includes("..")) {
    throw new Error(`Unsafe repository path: ${value || "<empty>"}`);
  }
  const absolute = path.resolve(root, relative);
  if (absolute !== root && !absolute.startsWith(`${root}${path.sep}`)) {
    throw new Error(`Path escapes repository: ${relative}`);
  }
  return relative;
}

function copyRepositoryFile(root, worktree, relative) {
  const safe = assertRelativePath(root, relative);
  const source = path.join(root, safe);
  if (!fs.existsSync(source) || !fs.statSync(source).isFile()) {
    throw new Error(`Transport source file not found: ${safe}`);
  }
  const target = path.join(worktree, safe);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
  return safe;
}

function randomRunIdentity() {
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  return `${stamp}-${crypto.randomBytes(5).toString("hex")}`;
}

function withBranchWorktree(root, branch, callback, { createFrom = "" } = {}) {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "autoscribe-git-"));
  const worktree = path.join(parent, "worktree");
  let added = false;
  try {
    const args = ["worktree", "add", "--quiet"];
    if (createFrom) args.push("-b", branch, worktree, createFrom);
    else args.push(worktree, branch);
    git(root, args);
    added = true;
    return callback(worktree);
  } finally {
    if (added) git(root, ["worktree", "remove", "--force", worktree], { allowFailure: true });
    fs.rmSync(parent, { recursive: true, force: true });
  }
}

function readJsonAtRef(root, ref, relative) {
  const result = git(root, ["show", `${ref}:${relative}`], { allowFailure: true });
  if (result.status !== 0) return null;
  try {
    return JSON.parse(String(result.stdout || ""));
  } catch (error) {
    throw new Error(`${ref}:${relative} contains invalid JSON: ${error.message}`);
  }
}

function frontmatterSlug(app, relative) {
  const file = app.vault.getAbstractFileByPath(relative);
  const slug = file ? app.metadataCache.getFileCache(file)?.frontmatter?.slug : "";
  const value = String(slug || "").trim();
  if (!value) throw new Error(`Selected file is missing a slug: ${relative}`);
  return value;
}

function pathTraversesSymlink(root, relative) {
  const safe = assertRelativePath(root, relative);
  const parts = safe.split("/");
  let current = root;
  for (const part of parts) {
    current = path.join(current, part);
    try {
      if (fs.lstatSync(current).isSymbolicLink()) return true;
    } catch {
      return false;
    }
  }
  return false;
}

function listInstructionPaths(app, root) {
  return app.vault.getMarkdownFiles()
    .filter((file) => {
      if (pathTraversesSymlink(root, file.path)) return false;
      const fm = app.metadataCache.getFileCache(file)?.frontmatter || {};
      const slug = String(fm.slug || "").trim();
      return String(fm.type || "").toLowerCase() === "instruction"
        || /^(rol|ctx|cxt|spc|ins)\./.test(slug)
        || file.path.startsWith("Instructions/");
    })
    .map((file) => file.path)
    .sort();
}

function planRelativePath(root, planRecord) {
  const absolute = path.resolve(String(planRecord?.path || ""));
  if (!absolute || !fs.existsSync(absolute)) throw new Error("Selected plan file was not found");
  return assertRelativePath(root, path.relative(root, absolute));
}

function commitSourceSnapshot(root, paths, subject) {
  const preexisting = git(root, ["diff", "--cached", "--quiet"], { allowFailure: true });
  if (preexisting.status === 1) {
    throw new Error("Dispatch cannot proceed while unrelated changes are already staged");
  }
  if (preexisting.status !== 0) throw new Error("Could not inspect the Git index");

  git(root, ["add", "--", ...paths]);
  const staged = git(root, ["diff", "--cached", "--quiet"], { allowFailure: true });
  if (staged.status === 1) git(root, ["commit", "--quiet", "-m", subject]);
  else if (staged.status !== 0) throw new Error("Could not inspect the dispatch snapshot");
  return headCommit(root);
}

function createDispatchBranch(app, { paths, planRecord, message = "", combineBasename = "" }) {
  const root = repositoryRoot(app);
  const sourceBranch = currentBranch(root);
  if (!sourceBranch) throw new Error("Dispatch requires a named source branch");
  if (sourceBranch.startsWith(RUN_BRANCH_PREFIX)) throw new Error("Cannot dispatch from a transport branch");

  const selected = [...new Set((paths || []).map((item) => assertRelativePath(root, item)))];
  if (!selected.length) throw new Error("Dispatch requires at least one selected file");

  const planSlug = String(planRecord?.record_identity || planRecord?.slug || "").trim();
  if (!planSlug) throw new Error("Selected plan is missing its identity");

  const runIdentity = randomRunIdentity();
  const branch = `${RUN_BRANCH_PREFIX}${runIdentity}`;
  const planPath = planRelativePath(root, planRecord);
  const instructionPaths = listInstructionPaths(app, root).map((item) => assertRelativePath(root, item));
  const snapshotPaths = [...new Set([...selected, planPath, ...instructionPaths])];
  const sourceSubject = String(message || "").trim() || `DISPATCH SOURCE ${planSlug}: ${runIdentity}`;
  const sourceCommit = commitSourceSnapshot(root, snapshotPaths, sourceSubject);
  let dispatchCommit = "";

  withBranchWorktree(root, branch, (worktree) => {
    const copied = new Set();
    for (const relative of [...selected, planPath, ...instructionPaths]) {
      if (!copied.has(relative)) {
        copyRepositoryFile(root, worktree, relative);
        copied.add(relative);
      }
    }

    const records = selected.map((relative) => ({
      identity: frontmatterSlug(app, relative),
      source_path: relative,
    }));

    const manifest = {
      version: 1,
      type: "autoscribe_dispatch",
      run_identity: runIdentity,
      branch,
      created_at: new Date().toISOString(),
      source_branch: sourceBranch,
      source_commit: sourceCommit,
      plan: { identity: planSlug, path: planPath },
      instructions: instructionPaths,
      combine: combineBasename ? { basename: String(combineBasename) } : null,
      records,
    };

    const manifestPath = path.join(worktree, DISPATCH_MANIFEST);
    fs.mkdirSync(path.dirname(manifestPath), { recursive: true });
    fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

    git(worktree, ["add", "--", ...copied, DISPATCH_MANIFEST]);
    git(worktree, ["commit", "--quiet", "-m", `DISPATCH ${planSlug}: ${runIdentity}`]);
    dispatchCommit = headCommit(worktree);
  }, { createFrom: sourceCommit });

  return {
    run_identity: runIdentity,
    branch,
    source_branch: sourceBranch,
    source_commit: sourceCommit,
    dispatch_commit: dispatchCommit,
    plan_identity: planSlug,
    count: selected.length,
  };
}

function listTransportRuns(app) {
  const root = repositoryRoot(app);
  const output = String(git(root, [
    "for-each-ref",
    "--format=%(refname:short)",
    `${RUN_REF_PREFIX}*`,
  ]).stdout || "");

  return output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((branch) => {
    const dispatch = readJsonAtRef(root, branch, DISPATCH_MANIFEST);
    if (!dispatch) return null;
    const response = readJsonAtRef(root, branch, RESPONSE_MANIFEST);
    const writeback = readJsonAtRef(root, branch, WRITEBACK_MANIFEST);
    return {
      branch,
      run_identity: dispatch.run_identity || branch.slice(RUN_BRANCH_PREFIX.length),
      created_at: dispatch.created_at || null,
      plan_identity: dispatch.plan?.identity || null,
      source_branch: dispatch.source_branch || null,
      source_commit: dispatch.source_commit || null,
      count: Array.isArray(dispatch.records) ? dispatch.records.length : 0,
      status: writeback ? "written_back" : response ? "response_ready" : "waiting",
      dispatch,
      response,
      writeback,
    };
  }).filter(Boolean).sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

function dispatchCommitForBranch(root, branch) {
  const result = git(root, ["log", branch, "--format=%H", "--diff-filter=A", "--", DISPATCH_MANIFEST], { allowFailure: true });
  return String(result.stdout || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean)[0] || "";
}

function splitFrontmatter(text) {
  const value = String(text || "");
  const match = value.match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n?)([\s\S]*)$/);
  return match ? { frontmatter: match[1], body: match[2] } : { frontmatter: "", body: value };
}

function showFile(root, ref, relative) {
  const result = git(root, ["show", `${ref}:${assertRelativePath(root, relative)}`], { allowFailure: true });
  if (result.status !== 0) throw new Error(`Could not read ${relative} from ${ref}`);
  return String(result.stdout || "");
}

function mergeBodies(root, currentBody, baseBody, responseBody) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "autoscribe-merge-"));
  try {
    const current = path.join(temp, "current.md");
    const base = path.join(temp, "base.md");
    const response = path.join(temp, "response.md");
    fs.writeFileSync(current, currentBody, "utf8");
    fs.writeFileSync(base, baseBody, "utf8");
    fs.writeFileSync(response, responseBody, "utf8");
    const result = runCommandSync("git", ["merge-file", "-p", current, base, response], {
      cwd: root,
      allowFailure: true,
      maxBuffer: 64 * 1024 * 1024,
    });
    if (![0, 1].includes(result.status)) {
      throw new Error(String(result.stderr || "git merge-file failed").trim());
    }
    return { content: String(result.stdout || ""), conflicted: result.status === 1 };
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

function requireCleanWorkingTree(root) {
  const output = String(git(root, ["status", "--porcelain"]).stdout || "");
  if (output.trim()) throw new Error("Write Responses requires a clean working tree");
}

function acknowledgeWriteback(root, branch, payload) {
  withBranchWorktree(root, branch, (worktree) => {
    const target = path.join(worktree, WRITEBACK_MANIFEST);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    git(worktree, ["add", "--", WRITEBACK_MANIFEST]);
    git(worktree, ["commit", "--quiet", "-m", `ACKNOWLEDGE ${payload.run_identity}`]);
  });
}

function applyResponseBranch(app, branch, { commitMessage = "" } = {}) {
  const root = repositoryRoot(app);
  const activeBranch = currentBranch(root);
  if (!activeBranch || activeBranch.startsWith(RUN_BRANCH_PREFIX)) {
    throw new Error("Write Responses must run from the editorial branch");
  }
  requireCleanWorkingTree(root);

  const dispatch = readJsonAtRef(root, branch, DISPATCH_MANIFEST);
  const response = readJsonAtRef(root, branch, RESPONSE_MANIFEST);
  const priorWriteback = readJsonAtRef(root, branch, WRITEBACK_MANIFEST);
  if (!dispatch) throw new Error(`Dispatch manifest not found on ${branch}`);
  if (!response) throw new Error(`Response manifest not found on ${branch}`);
  if (priorWriteback) throw new Error(`Response has already been written back: ${branch}`);

  const responseRecords = Array.isArray(response.records) && response.records.length
    ? response.records
    : dispatch.records;
  const dispatchByIdentity = new Map((dispatch.records || []).map((item) => [item.identity, item]));
  const written = [];
  const conflicts = [];

  for (const responseRecord of responseRecords || []) {
    const identity = String(responseRecord.identity || "").trim();
    const dispatchRecord = dispatchByIdentity.get(identity) || responseRecord;
    const sourcePath = assertRelativePath(root, responseRecord.path || responseRecord.source_path || dispatchRecord.source_path);
    const currentFile = app.vault.getMarkdownFiles().find((file) => {
      const slug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
      return slug === identity;
    });
    if (!currentFile) throw new Error(`Current vault file not found for ${identity}`);

    const currentPath = assertRelativePath(root, currentFile.path);
    const currentText = fs.readFileSync(path.join(root, currentPath), "utf8");
    const dispatchCommit = response.dispatch_commit || dispatchCommitForBranch(root, branch);
    if (!dispatchCommit) throw new Error(`Could not locate the dispatch commit for ${branch}`);
    const baseText = showFile(root, dispatchCommit, sourcePath);
    const responseText = showFile(root, branch, sourcePath);
    const current = splitFrontmatter(currentText);
    const base = splitFrontmatter(baseText);
    const returned = splitFrontmatter(responseText);
    const merged = mergeBodies(root, current.body, base.body, returned.body);
    fs.writeFileSync(path.join(root, currentPath), current.frontmatter + merged.content, "utf8");
    const item = { identity, path: currentPath, source_path: sourcePath };
    if (merged.conflicted) conflicts.push(item);
    else written.push(item);
  }

  if (conflicts.length) {
    return { branch, run_identity: dispatch.run_identity, written, conflicts, committed: false };
  }

  git(root, ["add", "--", ...written.map((item) => item.path)]);
  const subject = String(commitMessage || "").trim() || `WRITEBACK ${dispatch.run_identity}`;
  git(root, ["commit", "--quiet", "-m", subject]);
  const masterCommit = headCommit(root);
  acknowledgeWriteback(root, branch, {
    version: 1,
    type: "autoscribe_writeback",
    run_identity: dispatch.run_identity,
    branch,
    written_at: new Date().toISOString(),
    target_branch: activeBranch,
    target_commit: masterCommit,
    records: written,
  });

  return {
    branch,
    run_identity: dispatch.run_identity,
    written,
    conflicts: [],
    committed: true,
    target_branch: activeBranch,
    target_commit: masterCommit,
  };
}

module.exports = {
  DISPATCH_MANIFEST,
  RESPONSE_MANIFEST,
  WRITEBACK_MANIFEST,
  repositoryRoot,
  createDispatchBranch,
  listTransportRuns,
  applyResponseBranch,
};
