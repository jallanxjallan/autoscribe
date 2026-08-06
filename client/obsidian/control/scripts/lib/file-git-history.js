"use strict";
const path = require("node:path");
const fs = require("node:fs");
const { runCommandSync } = require("./shell.js");

function root(app) {
  const vault = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  return String(runCommandSync("git", ["-C", vault, "rev-parse", "--show-toplevel"]).stdout || "").trim();
}
function git(repo, args, options={}) { return runCommandSync("git", ["-C", repo, ...args], { maxBuffer: 64*1024*1024, ...options }); }
function repoPath(app, vaultPath) {
  const vault = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const repo = root(app);
  const rel = path.relative(repo, path.resolve(vault, vaultPath)).replace(/\\/g, "/");
  if (!rel || rel.startsWith("../") || path.isAbsolute(rel)) throw new Error(`Unsafe file path: ${vaultPath}`);
  return { repo, rel };
}
function liveState(app, vaultPath) {
  const { repo, rel } = repoPath(app, vaultPath);
  const status = String(git(repo, ["status", "--porcelain=v1", "--", rel]).stdout || "").trim();
  const latest = String(git(repo, ["log", "-1", "--format=%H%x1f%s%x1f%ct", "--", rel], {allowFailure:true}).stdout || "").trim();
  let commit = null;
  if (latest) { const [hash, subject, timestamp] = latest.split("\x1f"); commit = {hash, subject, timestamp:Number(timestamp||0)}; }
  return { path:vaultPath, repo_path:rel, status: status || "clean", dirty:Boolean(status), latest_commit:commit };
}
function lines(value) { return String(value || "").split(/\r?\n/).map(x=>x.trim()).filter(Boolean); }
function exactRefs(repo, hash) {
  return lines(git(repo, ["for-each-ref", "--points-at", hash, "--format=%(refname:short)", "refs/heads", "refs/remotes", "refs/tags"], {allowFailure:true}).stdout);
}
function transportRefs(repo, hash) {
  return lines(git(repo, ["for-each-ref", "--contains", hash, "--format=%(refname:short)", "refs/heads", "refs/remotes"], {allowFailure:true}).stdout)
    .filter(ref => /(^|\/)(autoscribe|transport|dispatch)(\/|$)/i.test(ref));
}
function fileChange(repo, rel, hash) {
  let out = String(git(repo, ["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", "-M", hash, "--", rel], {allowFailure:true}).stdout || "").trim();
  if (!out) return "Recorded";
  const code = out.split(/\s+/)[0] || "M";
  if (code.startsWith("A")) return "Added";
  if (code.startsWith("D")) return "Deleted";
  if (code.startsWith("R")) return "Renamed";
  if (code.startsWith("C")) return "Copied";
  return "Modified";
}
function fileSummary(repo, rel, hash) {
  const out = String(git(repo, ["show", "--format=", "--numstat", hash, "--", rel], {allowFailure:true}).stdout || "").trim();
  let added=0, deleted=0;
  for (const row of lines(out)) {
    const [a,d] = row.split(/\s+/);
    if (/^\d+$/.test(a)) added += Number(a);
    if (/^\d+$/.test(d)) deleted += Number(d);
  }
  return { added, deleted };
}
function classify(subject, refs) {
  const text = `${subject} ${refs.join(" ")}`.toLowerCase();
  if (/file-restore|restore/.test(text)) return "Restore";
  if (/(^|[\s/:_-])lock(ed)?([\s/:_-]|$)/.test(text)) return "Lock";
  if (/(^|[\s/:_-])version(ed)?([\s/:_-]|$)/.test(text)) return "Version";
  if (/dispatch|transport|inflight|autoscribe\/run/.test(text)) return "Transport";
  if (/write.?back|response/.test(text)) return "Writeback";
  return "Commit";
}
function history(app, vaultPath) {
  const { repo, rel } = repoPath(app, vaultPath);
  const head = String(git(repo,["rev-parse","HEAD"]).stdout||"").trim();
  const headFileCommit = String(git(repo,["log","-1","--format=%H","HEAD","--",rel],{allowFailure:true}).stdout||"").trim();
  const out = String(git(repo, ["log", "--all", "--follow", "--date=format-local:%d/%m/%Y %H:%M", "--format=%H%x1f%ad%x1f%an%x1f%s", "--", rel], {allowFailure:true}).stdout || "");
  const seen = new Set();
  return out.split(/\r?\n/).filter(Boolean).map(line => {
    const [hash,date,author,subject] = line.split("\x1f");
    if (seen.has(hash)) return null;
    seen.add(hash);
    const refs = exactRefs(repo, hash);
    const transport_refs = transportRefs(repo, hash);
    const stats = fileSummary(repo, rel, hash);
    return {
      hash,date,author,subject:subject || "(no commit message)",refs,transport_refs,
      kind: classify(subject || "", [...refs,...transport_refs]),
      change: fileChange(repo, rel, hash),
      added:stats.added, deleted:stats.deleted,
      is_head:hash===head, is_current_file_version:hash===headFileCommit
    };
  }).filter(Boolean);
}
function stashManifestPath(repo) {
  const gitDir = String(git(repo, ["rev-parse", "--git-dir"]).stdout || "").trim();
  return path.resolve(repo, gitDir, "autoscribe-file-stashes.json");
}
function readStashManifest(repo) {
  const file = stashManifestPath(repo);
  try {
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    return data && Array.isArray(data.items) ? data : { version:1, items:[] };
  } catch (_) { return { version:1, items:[] }; }
}
function writeStashManifest(repo, data) {
  const file = stashManifestPath(repo);
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n", "utf8");
}
function safeRefPart(value) {
  return String(value || "file").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "file";
}
function listFileStashes(app, vaultPath=null) {
  const repo = root(app);
  const manifest = readStashManifest(repo);
  return manifest.items.filter(item => !vaultPath || item.vault_path === vaultPath).sort((a,b) => b.created_at.localeCompare(a.created_at));
}
function stashCurrent(app, vaultPath) {
  const { repo, rel } = repoPath(app, vaultPath);
  const abs = path.join(repo, rel);
  if (!fs.existsSync(abs)) throw new Error("The selected file does not exist in the working tree.");
  const blob = String(git(repo, ["hash-object", "-w", "--", rel]).stdout || "").trim();
  if (!/^[0-9a-f]{40}$/.test(blob)) throw new Error("Git did not create a valid file snapshot.");
  const stamp = new Date().toISOString();
  const compact = stamp.replace(/[-:TZ.]/g, "").slice(0,14);
  const ref = `refs/autoscribe/file-stashes/${safeRefPart(rel)}/${compact}-${blob.slice(0,8)}`;
  git(repo, ["update-ref", ref, blob]);
  const head = String(git(repo, ["rev-parse", "HEAD"], {allowFailure:true}).stdout || "").trim();
  const manifest = readStashManifest(repo);
  const item = { id:`${compact}-${blob.slice(0,8)}`, vault_path:vaultPath, repo_path:rel, blob, ref, head, created_at:stamp };
  manifest.items.push(item);
  writeStashManifest(repo, manifest);
  return item;
}
function restoreFileStash(app, vaultPath, id) {
  const { repo, rel } = repoPath(app, vaultPath);
  const manifest = readStashManifest(repo);
  const item = manifest.items.find(x => x.id === id && x.repo_path === rel);
  if (!item) throw new Error("The selected stash no longer exists.");
  const content = git(repo, ["cat-file", "blob", item.blob]).stdout;
  fs.writeFileSync(path.join(repo, rel), content);
  git(repo, ["add", "--", rel]);
  return item;
}
function dropFileStash(app, vaultPath, id) {
  const { repo, rel } = repoPath(app, vaultPath);
  const manifest = readStashManifest(repo);
  const index = manifest.items.findIndex(x => x.id === id && x.repo_path === rel);
  if (index < 0) throw new Error("The selected stash no longer exists.");
  const [item] = manifest.items.splice(index, 1);
  git(repo, ["update-ref", "-d", item.ref], {allowFailure:true});
  writeStashManifest(repo, manifest);
  return item;
}

function restoreVersion(app, vaultPath, commit) {
  const { repo, rel } = repoPath(app, vaultPath);
  const dirty = String(git(repo,["status","--porcelain=v1","--",rel]).stdout||"").trim();
  if (dirty) throw new Error("The selected file has uncommitted changes. Commit or discard them before restoring an older version.");
  const valid = String(git(repo,["rev-parse","--verify",`${commit}^{commit}`]).stdout||"").trim();
  const head = String(git(repo,["rev-parse","HEAD"]).stdout||"").trim();
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g,"").slice(0,14);
  const safe = `autoscribe/file-restore/${stamp}-${head.slice(0,8)}`;
  git(repo,["tag",safe,head]);
  git(repo,["restore","--source",valid,"--staged","--worktree","--",rel]);
  return { source:valid, safety_tag:safe, head };
}
module.exports = { liveState, history, restoreVersion, listFileStashes, stashCurrent, restoreFileStash, dropFileStash };
