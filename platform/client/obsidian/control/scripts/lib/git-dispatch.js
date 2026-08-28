"use strict";

const path = require("node:path");
const { spawn } = require("node:child_process");
const { requireVaultBasePath } = require("./vault-paths.js");

function runGit(args, { cwd, input = "" } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, {
      cwd,
      env: process.env,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", (status) => {
      if (status === 0) return resolve({ stdout, stderr });
      const detail = (stderr || stdout || `git exited with status ${status}`).trim();
      reject(new Error(detail));
    });
    child.stdin.end(input);
  });
}

async function gitText(cwd, args) {
  const { stdout } = await runGit(args, { cwd });
  return String(stdout || "").trim();
}

async function repositoryRoot(app) {
  const vaultRoot = requireVaultBasePath(app);
  const root = await gitText(vaultRoot, ["rev-parse", "--show-toplevel"]);
  if (!root) throw new Error("Could not determine Git repository root.");
  return path.resolve(root);
}

async function editorialBranch(root) {
  let branch;
  try {
    branch = await gitText(root, ["symbolic-ref", "--quiet", "--short", "HEAD"]);
  } catch (_) {
    throw new Error("Dispatch Run requires a checked-out editorial branch; detached HEAD is not allowed.");
  }
  if (!branch) throw new Error("Dispatch Run could not determine the checked-out branch.");
  if (branch === "autoscribe/inflight" || branch.startsWith("autoscribe/")) {
    throw new Error(`Dispatch Run will not write AutoScribe-owned branch '${branch}'. Check out the editorial branch first.`);
  }
  return branch;
}

function normalizeRelativePath(root, vaultRoot, value) {
  const raw = String(value || "").trim();
  if (!raw) throw new Error("Dispatch selection contains an empty filepath.");

  const absolute = path.resolve(vaultRoot, raw);
  const relative = path.relative(root, absolute).replace(/\\/g, "/");
  if (!relative || relative === "." || relative.startsWith("../") || path.isAbsolute(relative)) {
    throw new Error(`Dispatch path is outside the Git repository: ${raw}`);
  }
  return relative;
}

async function requireTracked(root, relativePaths) {
  for (const relative of relativePaths) {
    try {
      await runGit(["ls-files", "--error-unmatch", "--", relative], { cwd: root });
    } catch (_) {
      throw new Error(`Dispatch target is not tracked by Git: ${relative}`);
    }
  }
}

function dispatchMessage(planSlug, documentSlugs) {
  const count = documentSlugs.length;
  const noun = count === 1 ? "document" : "documents";
  const lines = [
    `autoscribe: dispatch ${planSlug} (${count} ${noun})`,
    "",
    "Autoscribe-Dispatch: 1",
    `Autoscribe-Plan: ${planSlug}`,
    ...documentSlugs.map((slug) => `Autoscribe-Document: ${slug}`),
    "",
  ];
  return lines.join("\n");
}

async function createDispatchCommit(app, { planSlug, documents }) {
  const plan = String(planSlug || "").trim();
  if (!plan) throw new Error("Dispatch Run requires a plan slug.");
  if (!Array.isArray(documents) || !documents.length) {
    throw new Error("Dispatch Run requires at least one document.");
  }

  const vaultRoot = requireVaultBasePath(app);
  const root = await repositoryRoot(app);
  const branch = await editorialBranch(root);

  const slugs = [];
  const paths = [];
  const seenSlugs = new Set();
  const seenPaths = new Set();

  for (const document of documents) {
    const slug = String(document?.slug || "").trim();
    if (!slug) throw new Error(`Selected file is missing a slug: ${document?.path || "unknown path"}`);
    if (seenSlugs.has(slug)) throw new Error(`Duplicate document slug in dispatch selection: ${slug}`);

    const relative = normalizeRelativePath(root, vaultRoot, document?.path);
    if (seenPaths.has(relative)) throw new Error(`Duplicate filepath in dispatch selection: ${relative}`);

    seenSlugs.add(slug);
    seenPaths.add(relative);
    slugs.push(slug);
    paths.push(relative);
  }

  await requireTracked(root, paths);

  const message = dispatchMessage(plan, slugs);
  await runGit(
    ["commit", "--only", "--allow-empty", "--file=-", "--", ...paths],
    { cwd: root, input: message }
  );

  const commit = await gitText(root, ["rev-parse", "HEAD"]);
  const shortCommit = await gitText(root, ["rev-parse", "--short=10", "HEAD"]);

  return {
    ok: true,
    branch,
    commit,
    short_commit: shortCommit,
    plan_slug: plan,
    document_slugs: slugs,
    paths,
    count: paths.length,
  };
}

module.exports = {
  createDispatchCommit,
  dispatchMessage,
  editorialBranch,
  repositoryRoot,
  runGit,
};
