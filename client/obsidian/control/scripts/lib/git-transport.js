"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runCommandSync } = require("./shell.js");

const RUN_REF_PREFIX = "refs/heads/autoscribe/run/";
const RUN_BRANCH_PREFIX = "autoscribe/run/";
const DISPATCH_MANIFEST = ".autoscribe/dispatch.json";
const RESULTS_DIR = ".autoscribe/results";
const DECISIONS_DIR = ".autoscribe/decisions";

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

function listFilesAtRef(root, ref, relativeDir) {
  const result = git(root, ["ls-tree", "-r", "--name-only", ref, "--", relativeDir], { allowFailure: true });
  if (result.status !== 0) return [];
  return String(result.stdout || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function resultIdentity(record, fallback = "") {
  return String(record?.record_identity || record?.source_identity || record?.identity || fallback || "").trim();
}

function readResultRecords(root, branch) {
  return listFilesAtRef(root, branch, RESULTS_DIR)
    .filter((relative) => relative.endsWith(".json"))
    .map((relative) => {
      const record = readJsonAtRef(root, branch, relative);
      if (!record) return null;
      const identity = resultIdentity(record, path.basename(relative, ".json"));
      return {
        ...record,
        identity,
        result_path: relative,
        source_path: String(record.source_path || "").trim(),
        content: String(record.content ?? record.record_content ?? ""),
      };
    })
    .filter((record) => record?.identity);
}

function readDecisionRecords(root, branch) {
  const decisions = new Map();
  for (const relative of listFilesAtRef(root, branch, DECISIONS_DIR).filter((item) => item.endsWith(".json"))) {
    const decision = readJsonAtRef(root, branch, relative);
    const identity = resultIdentity(decision, path.basename(relative, ".json"));
    if (decision && identity) decisions.set(identity, { ...decision, identity, decision_path: relative });
  }
  return decisions;
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
    const results = readResultRecords(root, branch);
    const decisions = readDecisionRecords(root, branch);
    const pending = results.filter((record) => !decisions.has(record.identity));
    return {
      branch,
      run_identity: dispatch.run_identity || branch.slice(RUN_BRANCH_PREFIX.length),
      created_at: dispatch.created_at || null,
      plan_identity: dispatch.plan?.identity || null,
      source_branch: dispatch.source_branch || null,
      source_commit: dispatch.source_commit || null,
      count: Array.isArray(dispatch.records) ? dispatch.records.length : 0,
      status: pending.length ? "response_pending" : results.length ? "reviewed" : "waiting",
      dispatch,
      results,
      decisions: [...decisions.values()],
      pending,
    };
  }).filter(Boolean).sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

function splitFrontmatter(text) {
  const value = String(text || "");
  const match = value.match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n?)([\s\S]*)$/);
  return match ? { frontmatter: match[1], body: match[2] } : { frontmatter: "", body: value };
}

function safeTagPart(value) {
  return String(value || "unknown")
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unknown";
}

function createOutcomeTag(root, commit, { runIdentity, identity, outcome, side }) {
  const tag = `autoscribe/${safeTagPart(runIdentity)}/${safeTagPart(identity)}/${outcome}/${side}`;
  git(root, ["tag", "-f", tag, commit]);
  return tag;
}

function currentRecordPath(app, identity, fallbackPath = "") {
  const match = app.vault.getMarkdownFiles().find((file) => {
    const slug = String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim();
    return slug === identity;
  });
  if (match) return match.path;
  if (fallbackPath) {
    const fallback = app.vault.getAbstractFileByPath(fallbackPath);
    if (fallback?.extension === "md") return fallback.path;
  }
  throw new Error(`Current vault file not found for ${identity}`);
}

function getResponseReview(app, branch, identity) {
  const root = repositoryRoot(app);
  const dispatch = readJsonAtRef(root, branch, DISPATCH_MANIFEST);
  if (!dispatch) throw new Error(`Dispatch manifest not found on ${branch}`);
  const result = readResultRecords(root, branch).find((item) => item.identity === identity);
  if (!result) throw new Error(`Result not found for ${identity} on ${branch}`);
  const decision = readDecisionRecords(root, branch).get(identity) || null;
  const dispatchRecord = (dispatch.records || []).find((item) => item.identity === identity) || {};
  const sourcePath = currentRecordPath(app, identity, result.source_path || dispatchRecord.source_path || "");
  const sourceText = fs.readFileSync(path.join(root, assertRelativePath(root, sourcePath)), "utf8");
  return {
    branch,
    run_identity: dispatch.run_identity,
    identity,
    source_path: sourcePath,
    source_text: sourceText,
    source_body: splitFrontmatter(sourceText).body,
    response_text: result.content,
    response_body: splitFrontmatter(result.content).body,
    result,
    decision,
  };
}

function assertEditorialBranch(root, dispatch) {
  const active = currentBranch(root);
  if (!active || active.startsWith(RUN_BRANCH_PREFIX)) throw new Error("Write Responses must run from the editorial branch");
  if (dispatch.source_branch && active !== dispatch.source_branch) {
    throw new Error(`Switch to source branch ${dispatch.source_branch} before reviewing this response`);
  }
  return active;
}

function commitSourceDecision(root, { path: sourcePath, runIdentity, identity, outcome }) {
  if (outcome === "declined") {
    const staged = git(root, ["diff", "--cached", "--quiet"], { allowFailure: true });
    if (staged.status === 1) throw new Error("Decline cannot proceed while unrelated changes are staged");
    if (staged.status !== 0) throw new Error("Could not inspect the Git index");
  }
  if (outcome === "accepted") git(root, ["add", "--", sourcePath]);
  const args = ["commit", "--quiet", "--allow-empty", "-m", `RESPONSE ${outcome.toUpperCase()} ${identity}: ${runIdentity}`];
  if (outcome === "accepted") args.push("--", sourcePath);
  git(root, args);
  return headCommit(root);
}

function commitBranchDecision(root, branch, payload) {
  return withBranchWorktree(root, branch, (worktree) => {
    const relative = `${DECISIONS_DIR}/${safeTagPart(payload.identity)}.json`;
    const target = path.join(worktree, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    git(worktree, ["add", "--", relative]);
    git(worktree, ["commit", "--quiet", "-m", `RESPONSE ${payload.outcome.toUpperCase()} ${payload.identity}`]);
    return headCommit(worktree);
  });
}

function decideResponse(app, branch, identity, outcome) {
  if (!["accepted", "declined"].includes(outcome)) throw new Error(`Unknown response decision: ${outcome}`);
  const root = repositoryRoot(app);
  const dispatch = readJsonAtRef(root, branch, DISPATCH_MANIFEST);
  if (!dispatch) throw new Error(`Dispatch manifest not found on ${branch}`);
  const activeBranch = assertEditorialBranch(root, dispatch);
  const review = getResponseReview(app, branch, identity);
  if (review.decision) throw new Error(`${identity} has already been ${review.decision.outcome}`);

  if (outcome === "accepted") {
    const current = splitFrontmatter(review.source_text);
    fs.writeFileSync(path.join(root, review.source_path), current.frontmatter + review.response_body, "utf8");
  }

  const sourceCommit = commitSourceDecision(root, {
    path: review.source_path,
    runIdentity: dispatch.run_identity,
    identity,
    outcome,
  });
  const payload = {
    version: 1,
    type: "autoscribe_response_decision",
    run_identity: dispatch.run_identity,
    branch,
    identity,
    source_path: review.source_path,
    outcome,
    decided_at: new Date().toISOString(),
    source_branch: activeBranch,
    source_commit: sourceCommit,
    result_identity: review.result.result_identity || review.result.call_identity || null,
  };
  const branchCommit = commitBranchDecision(root, branch, payload);
  const sourceTag = createOutcomeTag(root, sourceCommit, {
    runIdentity: dispatch.run_identity,
    identity,
    outcome,
    side: "source",
  });
  const branchTag = createOutcomeTag(root, branchCommit, {
    runIdentity: dispatch.run_identity,
    identity,
    outcome,
    side: "flight",
  });
  return { ...payload, branch_commit: branchCommit, source_tag: sourceTag, branch_tag: branchTag };
}

module.exports = {
  DISPATCH_MANIFEST,
  RESULTS_DIR,
  DECISIONS_DIR,
  repositoryRoot,
  createDispatchBranch,
  listTransportRuns,
  getResponseReview,
  decideResponse,
};
