"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runCommandSync } = require("./shell.js");

const RUN_REF_PREFIX = "refs/heads/autoscribe/run/";
const RUN_BRANCH_PREFIX = "autoscribe/run/";
const RESULTS_DIR = ".autoscribe/results";

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

function commitMessage(root, commit) {
  return String(git(root, ["show", "-s", "--format=%B", commit]).stdout || "");
}

function parseDispatchMessage(message, branch = "") {
  const lines = String(message || "").split(/\r?\n/);
  if (lines[0]?.trim() !== "AUTOSCRIBE DISPATCH") return null;
  const values = {};
  const records = [];
  const instructions = [];
  for (const line of lines.slice(1)) {
    const match = line.match(/^([A-Za-z-]+):\s*(.*)$/);
    if (!match) continue;
    const [, key, raw] = match;
    if (key === "Record") {
      const [identity, ...rest] = raw.split("\t");
      const source_path = rest.join("\t").trim();
      if (identity.trim() && source_path) records.push({ identity: identity.trim(), source_path });
    } else if (key === "Instruction") {
      if (raw.trim()) instructions.push(raw.trim());
    } else values[key] = raw.trim();
  }
  return {
    run_identity: values.Run || branch.slice(RUN_BRANCH_PREFIX.length),
    branch,
    created_at: values.Created || null,
    source_branch: values["Source-Branch"] || null,
    source_commit: values["Source-Commit"] || null,
    plan: { identity: values.Plan || null, path: values["Plan-Path"] || null },
    combine: values["Combine-Basename"] ? { basename: values["Combine-Basename"] } : null,
    records,
    instructions,
  };
}

function dispatchCommit(root, branch) {
  const output = String(git(root, ["log", "--format=%H%x09%s", branch]).stdout || "");
  for (const line of output.split(/\r?\n/)) {
    const [commit, subject] = line.split("\t", 2);
    if (subject === "AUTOSCRIBE DISPATCH") return commit;
  }
  return "";
}

function readDispatch(root, branch) {
  const commit = dispatchCommit(root, branch);
  return commit ? parseDispatchMessage(commitMessage(root, commit), branch) : null;
}

function gitTagExists(root, tag) {
  return git(root, ["rev-parse", "-q", "--verify", `refs/tags/${tag}`], { allowFailure: true }).status === 0;
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

function referencedInstructionSlugs(planRecord) {
  const steps = planRecord?.payload?.steps;
  const values = steps && typeof steps === "object" ? Object.values(steps) : [];
  const slugs = new Set();

  const remember = (value) => {
    const slug = String(value || "").trim();
    if (slug) slugs.add(slug);
  };

  for (const step of values) {
    remember(step?.instruction);
    const groups = step?.instruction_slugs;
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) continue;
    for (const key of ["role", "context", "specifics", "instructions"]) {
      const entries = Array.isArray(groups[key]) ? groups[key] : [];
      for (const entry of entries) remember(entry);
    }
  }
  return [...slugs];
}

function listInstructionPaths(app, root, planRecord) {
  const wanted = referencedInstructionSlugs(planRecord);
  if (!wanted.length) return [];

  const bySlug = new Map();
  for (const file of app.vault.getMarkdownFiles()) {
    if (pathTraversesSymlink(root, file.path)) continue;
    const fm = app.metadataCache.getFileCache(file)?.frontmatter || {};
    const slug = String(fm.slug || "").trim();
    if (slug && wanted.includes(slug)) bySlug.set(slug, file.path);
  }

  const missing = wanted.filter((slug) => !bySlug.has(slug));
  if (missing.length) {
    throw new Error(`Selected plan references missing instruction slug${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`);
  }

  return wanted.map((slug) => bySlug.get(slug)).sort();
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
  const instructionPaths = listInstructionPaths(app, root, planRecord).map((item) => assertRelativePath(root, item));
  const snapshotPaths = [...new Set([...selected, planPath, ...instructionPaths])];
  const sourceSubject = String(message || "").trim() || `DISPATCH SOURCE ${planSlug}: ${runIdentity}`;
  const sourceCommit = commitSourceSnapshot(root, snapshotPaths, sourceSubject);
  const records = selected.map((relative) => ({ identity: frontmatterSlug(app, relative), source_path: relative }));
  let dispatchCommitHash = "";

  withBranchWorktree(root, branch, (worktree) => {
    const copied = new Set();
    for (const relative of snapshotPaths) {
      copyRepositoryFile(root, worktree, relative);
      copied.add(relative);
    }
    git(worktree, ["add", "--", ...copied]);
    const body = [
      "Run: " + runIdentity,
      "Created: " + new Date().toISOString(),
      "Plan: " + planSlug,
      "Plan-Path: " + planPath,
      "Source-Branch: " + sourceBranch,
      "Source-Commit: " + sourceCommit,
      ...(combineBasename ? ["Combine-Basename: " + String(combineBasename)] : []),
      ...records.map((row) => `Record: ${row.identity}\t${row.source_path}`),
      ...instructionPaths.map((relative) => `Instruction: ${relative}`),
    ].join("\n");
    git(worktree, [
      "commit",
      "--quiet",
      "--allow-empty",
      "-m",
      "AUTOSCRIBE DISPATCH",
      "-m",
      body,
    ]);
    dispatchCommitHash = headCommit(worktree);
  }, { createFrom: sourceCommit });

  return { run_identity: runIdentity, branch, source_branch: sourceBranch, source_commit: sourceCommit,
    dispatch_commit: dispatchCommitHash, plan_identity: planSlug, count: selected.length };
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

function decisionFor(root, runIdentity, identity) {
  const prefix = `autoscribe/decision/${safeTagPart(runIdentity)}/${safeTagPart(identity)}/`;
  const output = String(git(root, ["tag", "--list", `${prefix}*`]).stdout || "").trim();
  const tag = output.split(/\r?\n/).find(Boolean);
  if (!tag) return null;
  const outcome = tag.slice(prefix.length).split("/")[0];
  const commit = String(git(root, ["rev-list", "-n", "1", tag]).stdout || "").trim();
  return { identity, outcome, tag, commit };
}

function listTransportRuns(app) {
  const root = repositoryRoot(app);
  const output = String(git(root, ["for-each-ref", "--format=%(refname:short)", `${RUN_REF_PREFIX}*`]).stdout || "");
  return output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((branch) => {
    const dispatch = readDispatch(root, branch);
    if (!dispatch) return null;
    const results = readResultRecords(root, branch);
    const decisions = dispatch.records.map((row) => decisionFor(root, dispatch.run_identity, row.identity)).filter(Boolean);
    const decided = new Set(decisions.map((item) => item.identity));
    const pending = results.filter((record) => !decided.has(record.identity));
    return { branch, run_identity: dispatch.run_identity, created_at: dispatch.created_at,
      plan_identity: dispatch.plan?.identity || null, source_branch: dispatch.source_branch,
      source_commit: dispatch.source_commit, count: dispatch.records.length,
      status: pending.length ? "response_pending" : results.length ? "reviewed" : gitTagExists(root, `autoscribe/claimed/${safeTagPart(dispatch.run_identity)}`) ? "waiting" : "unclaimed",
      dispatch, results, decisions, pending };
  }).filter(Boolean).sort((a,b) => String(b.created_at||"").localeCompare(String(a.created_at||"")));
}

function splitFrontmatter(text) {
  const value = String(text || "");
  const match = value.match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n?)([\s\S]*)$/);
  return match ? { frontmatter: match[1], body: match[2] } : { frontmatter: "", body: value };
}

function updateMachineFrontmatter(text, { action = null } = {}) {
  const parts = splitFrontmatter(text);
  if (!parts.frontmatter) {
    if (!action) return text;
    return `---\naction: ${action}\n---\n${parts.body}`;
  }

  const newline = parts.frontmatter.includes("\r\n") ? "\r\n" : "\n";
  const raw = parts.frontmatter.replace(/^---\r?\n/, "").replace(/\r?\n---\r?\n?$/, "");
  const input = raw.split(/\r?\n/);
  const output = [];
  for (let i = 0; i < input.length; i += 1) {
    const line = input[i];
    if (/^action\s*:/.test(line) && action) continue;
    // Remove legacy nested pipeline metadata. Operational state now lives in Git
    // and is reconstructed by File State rather than copied into frontmatter.
    if (/^pipeline\s*:/.test(line)) {
      i += 1;
      while (i < input.length && (/^\s+/.test(input[i]) || input[i].trim() === "")) i += 1;
      i -= 1;
      continue;
    }
    output.push(line);
  }
  if (action) {
    const slugAt = output.findIndex((line) => /^slug\s*:/.test(line));
    output.splice(slugAt >= 0 ? slugAt + 1 : output.length, 0, `action: ${action}`);
  }
  return `---${newline}${output.join(newline)}${newline}---${newline}${parts.body}`;
}

function clearPipelineMetadata(app, paths) {
  const root = repositoryRoot(app);
  for (const relative of paths) {
    const safe = assertRelativePath(root, relative);
    const absolute = path.join(root, safe);
    const original = fs.readFileSync(absolute, "utf8");
    const frontmatter = splitFrontmatter(original).frontmatter;
    if (!frontmatter || !/^action\s*:\s*\S+/m.test(frontmatter)) {
      throw new Error(`Selected file is missing required action property: ${safe}`);
    }
    const updated = updateMachineFrontmatter(original);
    if (updated !== original) fs.writeFileSync(absolute, updated, "utf8");
  }
}

function safeTagPart(value) {
  return String(value || "unknown").trim().replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "unknown";
}

function currentRecordPath(app, identity, fallbackPath = "") {
  const match = app.vault.getMarkdownFiles().find((file) => String(app.metadataCache.getFileCache(file)?.frontmatter?.slug || "").trim() === identity);
  if (match) return match.path;
  if (fallbackPath) { const fallback = app.vault.getAbstractFileByPath(fallbackPath); if (fallback?.extension === "md") return fallback.path; }
  throw new Error(`Current vault file not found for ${identity}`);
}

function getResponseReview(app, branch, identity) {
  const root = repositoryRoot(app);
  const dispatch = readDispatch(root, branch);
  if (!dispatch) throw new Error(`Dispatch commit not found on ${branch}`);
  const result = readResultRecords(root, branch).find((item) => item.identity === identity);
  if (!result) throw new Error(`Result not found for ${identity} on ${branch}`);
  const decision = decisionFor(root, dispatch.run_identity, identity);
  const dispatchRecord = dispatch.records.find((item) => item.identity === identity) || {};
  const sourcePath = currentRecordPath(app, identity, result.source_path || dispatchRecord.source_path || "");
  const sourceText = fs.readFileSync(path.join(root, assertRelativePath(root, sourcePath)), "utf8");
  return { branch, run_identity: dispatch.run_identity, identity, source_path: sourcePath, source_text: sourceText,
    source_body: splitFrontmatter(sourceText).body, response_text: result.content,
    response_body: splitFrontmatter(result.content).body, result, decision };
}

function getArchivedResponseReview(app, branch, identity) {
  const root = repositoryRoot(app);
  const dispatch = readDispatch(root, branch);
  if (!dispatch) throw new Error(`Dispatch commit not found on ${branch}`);
  const result = readResultRecords(root, branch).find((item) => item.identity === identity);
  if (!result) throw new Error(`Result not found for ${identity} on ${branch}`);
  const dispatchRecord = dispatch.records.find((item) => item.identity === identity) || {};
  const sourcePath = result.source_path || dispatchRecord.source_path || currentRecordPath(app, identity, "");
  const source = git(root, ["show", `${dispatch.source_commit}:${sourcePath}`]);
  const sourceText = String(source.stdout || "");
  return { branch, run_identity: dispatch.run_identity, identity, source_path: sourcePath, source_text: sourceText,
    source_body: splitFrontmatter(sourceText).body, response_text: result.content, response_body: splitFrontmatter(result.content).body,
    result, decision: decisionFor(root, dispatch.run_identity, identity) };
}

function assertEditorialBranch(root, dispatch) {
  const active = currentBranch(root);
  if (!active || active.startsWith(RUN_BRANCH_PREFIX)) throw new Error("Write Responses must run from the editorial branch");
  if (dispatch.source_branch && active !== dispatch.source_branch) throw new Error(`Switch to source branch ${dispatch.source_branch} before reviewing this response`);
  return active;
}

function commitSourceDecision(root, { path: sourcePath, runIdentity, identity, outcome }) {
  if (outcome === "declined") {
    const staged = git(root, ["diff", "--cached", "--quiet"], { allowFailure: true });
    if (staged.status === 1) throw new Error("Decline cannot proceed while unrelated changes are staged");
    if (staged.status !== 0) throw new Error("Could not inspect the Git index");
  }
  if (outcome === "accepted") git(root, ["add", "--", sourcePath]);
  const args = ["commit", "--quiet", "--allow-empty", "-m", `AUTOSCRIBE RESPONSE ${outcome.toUpperCase()}`, "-m", `Run: ${runIdentity}\nRecord: ${identity}\nSource-Path: ${sourcePath}`];
  if (outcome === "accepted") args.push("--", sourcePath);
  git(root, args);
  return headCommit(root);
}

function commitBranchDecision(root, branch, payload) {
  return withBranchWorktree(root, branch, (worktree) => {
    git(worktree, ["commit", "--quiet", "--allow-empty", "-m", `AUTOSCRIBE DECISION ${payload.outcome.toUpperCase()}`, "-m",
      `Run: ${payload.run_identity}\nRecord: ${payload.identity}\nSource-Path: ${payload.source_path}\nSource-Commit: ${payload.source_commit}`]);
    return headCommit(worktree);
  });
}

function decideResponse(app, branch, identity, outcome) {
  if (!["accepted", "declined"].includes(outcome)) throw new Error(`Unknown response decision: ${outcome}`);
  const root = repositoryRoot(app);
  const dispatch = readDispatch(root, branch);
  if (!dispatch) throw new Error(`Dispatch commit not found on ${branch}`);
  const activeBranch = assertEditorialBranch(root, dispatch);
  const review = getResponseReview(app, branch, identity);
  if (review.decision) throw new Error(`${identity} has already been ${review.decision.outcome}`);
  if (outcome === "accepted") {
    const current = splitFrontmatter(review.source_text);
    const accepted = updateMachineFrontmatter(current.frontmatter + review.response_body, {
      action: "human-review",
    });
    fs.writeFileSync(path.join(root, review.source_path), accepted, "utf8");
  }
  const sourceCommit = commitSourceDecision(root, { path: review.source_path, runIdentity: dispatch.run_identity, identity, outcome });
  const payload = { run_identity: dispatch.run_identity, branch, identity, source_path: review.source_path, outcome,
    decided_at: new Date().toISOString(), source_branch: activeBranch, source_commit: sourceCommit };
  const branchCommit = commitBranchDecision(root, branch, payload);
  const tag = `autoscribe/decision/${safeTagPart(dispatch.run_identity)}/${safeTagPart(identity)}/${outcome}`;
  git(root, ["tag", "-f", tag, branchCommit]);
  return { ...payload, branch_commit: branchCommit, branch_tag: tag };
}

function pipelineStateForPath(app, sourcePath) {
  const safePath = String(sourcePath || "").replace(/\\/g, "/");
  const root = repositoryRoot(app);
  const matches = listTransportRuns(app).flatMap((run) => {
    const record = run.dispatch.records.find((item) => item.source_path === safePath);
    if (!record) return [];
    const result = run.results.find((item) => item.identity === record.identity) || null;
    const decision = decisionFor(root, run.run_identity, record.identity);
    let state = run.status;
    if (decision?.outcome === "accepted") state = "written-back";
    else if (decision?.outcome === "declined") state = "declined";
    else if (result) state = "response-pending";
    return [{
      state,
      run_identity: run.run_identity,
      plan_identity: run.plan_identity || null,
      branch: run.branch,
      created_at: run.created_at || null,
      source_commit: run.source_commit || null,
      identity: record.identity,
      result: Boolean(result),
      decision: decision?.outcome || null,
    }];
  });
  return matches.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0] || null;
}

function responseHistoryForPath(app, sourcePath) {
  const safePath = String(sourcePath || "").replace(/\\/g, "/");
  return listTransportRuns(app).flatMap((run) => run.results
    .filter((record) => (record.source_path || run.dispatch.records.find((item) => item.identity === record.identity)?.source_path) === safePath)
    .map((record) => ({ ...run, record, decision: decisionFor(repositoryRoot(app), run.run_identity, record.identity) })))
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

function reconsiderResponse(app, branch, identity, outcome) {
  if (!["accepted", "declined"].includes(outcome)) throw new Error(`Unknown response decision: ${outcome}`);
  const root = repositoryRoot(app);
  const dispatch = readDispatch(root, branch);
  if (!dispatch) throw new Error(`Dispatch commit not found on ${branch}`);
  assertEditorialBranch(root, dispatch);
  const review = getResponseReview(app, branch, identity);
  const existing = review.decision;
  if (!existing) return decideResponse(app, branch, identity, outcome);
  if (existing.outcome === outcome) throw new Error(`${identity} is already ${outcome}`);
  const status = git(root, ["status", "--porcelain=v1", "--", review.source_path]);
  if (String(status.stdout || "").trim()) throw new Error(`Cannot reconsider while ${review.source_path} has uncommitted changes`);

  if (outcome === "accepted") {
    const current = splitFrontmatter(review.source_text);
    const accepted = updateMachineFrontmatter(current.frontmatter + review.response_body, {
      action: "human-review",
    });
    fs.writeFileSync(path.join(root, review.source_path), accepted, "utf8");
  } else {
    const restored = git(root, ["show", `${dispatch.source_commit}:${review.source_path}`]);
    fs.writeFileSync(path.join(root, review.source_path), String(restored.stdout || ""), "utf8");
  }
  git(root, ["tag", "-d", existing.tag], { allowFailure: true });
  git(root, ["add", "--", review.source_path]);
  git(root, ["commit", "--quiet", "-m", `AUTOSCRIBE RESPONSE RECONSIDERED: ${outcome.toUpperCase()}`, "-m", `Run: ${dispatch.run_identity}\nRecord: ${identity}\nSource-Path: ${review.source_path}`, "--", review.source_path]);
  const sourceCommit = headCommit(root);
  const payload = { run_identity: dispatch.run_identity, branch, identity, source_path: review.source_path, outcome, decided_at: new Date().toISOString(), source_branch: currentBranch(root), source_commit: sourceCommit };
  const branchCommit = commitBranchDecision(root, branch, payload);
  const tag = `autoscribe/decision/${safeTagPart(dispatch.run_identity)}/${safeTagPart(identity)}/${outcome}`;
  git(root, ["tag", "-f", tag, branchCommit]);
  return { ...payload, branch_commit: branchCommit, branch_tag: tag, reconsidered: true };
}

module.exports = {
  RESULTS_DIR,
  repositoryRoot,
  createDispatchBranch,
  listTransportRuns,
  getResponseReview,
  getArchivedResponseReview,
  decideResponse,
  clearPipelineMetadata,
  responseHistoryForPath,
  pipelineStateForPath,
  reconsiderResponse,
};
