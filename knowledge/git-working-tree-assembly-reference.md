# Git Working-Tree Assembly Reference

## Purpose

Use a Git working tree as an **assembly point** for files whose authoritative histories live in different repositories.

This is especially useful for Obsidian vaults, publishing projects, web-posting projects, build pipelines, and any workflow where:

- one repository owns project/content history;
- another repository owns shared configuration, templates, scripts, macros, hotkeys, CSS, Typst/Pandoc assets, etc.;
- the final working directory needs files from both;
- you do **not** want all those files pushed to the same remote.

The key Git distinction is:

> A file can be present in a working tree without being tracked by the working tree's main repository.

A remote supplies history. The working tree supplies the environment. You decide which files the local repository owns.

---

## 1. The basic model

For an Obsidian vault:

```text
vault working tree
├── manuscript/                 tracked by vault Git repo
├── notes/                      tracked by vault Git repo
├── .obsidian/
│   ├── app.json                perhaps local/vault-owned
│   └── hotkeys.json            imported from config repo, ignored locally
├── scripts/
│   └── autoscribe/             imported from config repo, ignored locally
└── templates/                  imported from config repo, ignored locally
```

The vault has two remotes with different jobs:

```text
safety  -> remote history/backup for this vault
config  -> shared upstream source of reusable files
```

The `safety` remote is the destination for the vault's own commits.

The `config` remote is **not** merged into the vault. It is simply fetched so that selected files can be copied from it into the working tree.

---

## 2. Create a vault normally

There is no need to clone a vault template.

Create each vault using native Obsidian functions. Install the small number of required plugins manually and configure whatever is genuinely vault-specific.

Then initialize Git inside the new vault:

```bash
git init
```

If necessary, establish the initial branch explicitly:

```bash
git branch -M main
```

---

## 3. Add the two remotes

Add the vault-specific backup/history remote:

```bash
git remote add safety <vault-specific-repository-url>
```

Add the common configuration repository:

```bash
git remote add config <shared-config-repository-url>
```

Check them:

```bash
git remote -v
```

Conceptually:

```text
safety = this project's history
config = optional reusable components
```

The fact that both are Git remotes does **not** mean they have to contain the same history or be merged together.

---

## 4. Fetch the config repository

Fetch its refs and objects:

```bash
git fetch config
```

This brings the `config` repository's objects into the local Git object database and gives you refs such as:

```text
config/main
```

It does **not** modify the working tree.

It does **not** merge anything.

It does **not** commit anything.

---

## 5. Do not `git pull config`

Avoid this:

```bash
git pull config main
```

`git pull` normally means:

```text
fetch + merge/rebase a branch into the current branch
```

That is not the desired architecture.

You want:

```text
fetch config
copy selected paths from config/main
```

This keeps the histories independent.

---

## 6. Import a config file without tracking it locally

Suppose the config repo contains:

```text
.obsidian/hotkeys.json
scripts/ui/dispatch-run.js
templates/chapter.md
```

To copy one file into the vault working tree:

```bash
git show config/main:.obsidian/hotkeys.json > .obsidian/hotkeys.json
```

For a script:

```bash
mkdir -p scripts/ui
git show config/main:scripts/ui/dispatch-run.js > scripts/ui/dispatch-run.js
```

For a template:

```bash
mkdir -p templates
git show config/main:templates/chapter.md > templates/chapter.md
```

`git show <ref>:<path>` asks Git to return the exact file contents stored at that path in that commit/ref.

The shell redirection (`>`) writes those bytes into the current working tree.

This is a very useful primitive:

```text
remote Git object -> stdout -> ordinary local file
```

No merge is involved.

---

## 7. Keep config files out of the safety repository

If imported config files must **never** be committed to the vault's `safety` history, ignore them in the vault repository.

Example `.gitignore`:

```gitignore
# Shared Obsidian configuration supplied by config remote
.obsidian/hotkeys.json

# Shared AutoScribe/UI machinery
scripts/ui/

# Shared templates
templates/shared/
```

Now those files can exist and function normally in the vault but remain outside the vault Git history.

Check:

```bash
git status --ignored
```

An ignored imported file should not appear as a normal untracked/staged file.

### Important principle

Git does not have a normal per-remote rule saying:

```text
commit this file but do not push it to remote X
```

A Git commit is a snapshot. When that commit is pushed, all tracked files represented by it are part of the pushed history.

Therefore the clean solution is:

```text
config-owned file -> present locally -> ignored by vault repo -> never in safety commits
```

---

## 8. Why `git show` is preferable here to `git restore`

Git can copy paths from another ref with commands such as:

```bash
git restore --source=config/main -- path/to/file
```

That is useful when you deliberately want the current repository to own the imported file.

For the untracked/ignored config model, this is clearer:

```bash
git show config/main:path/to/file > path/to/file
```

It explicitly treats the config repository as a **source of bytes** rather than as part of the vault's tracked tree.

Use `git restore` when vendoring/tracking is intended.

Use `git show ... > file` when the imported file should remain outside the local repository's ownership.

---

## 9. Two valid import modes

### A. Runtime/config import — not tracked locally

Use when the source repository remains authoritative.

```text
config repo owns file
       |
       | fetch + git show
       v
working tree copy
       |
       X not committed
safety repo
```

Typical examples:

- hotkeys;
- common macros;
- shared UI scripts;
- CSS snippets;
- build helpers;
- common templates.

Put the target paths in `.gitignore`.

### B. Vendored import — tracked locally

Use when the project should take ownership of the imported version.

```bash
git fetch config
git restore --source=config/main -- path/to/file
git add path/to/file
git commit
```

Now the imported file belongs to the content/vault repo until you deliberately update it again.

Typical reasons:

- freezing a publication against a known template version;
- making project-specific modifications;
- requiring a completely reproducible checkout from one repository;
- preserving an exact historical release.

Both approaches are legitimate. Choose ownership deliberately.

---

## 10. Updating shared files later

Refresh the remote refs:

```bash
git fetch config
```

Then overwrite selected local copies:

```bash
git show config/main:.obsidian/hotkeys.json > .obsidian/hotkeys.json

git show config/main:scripts/ui/dispatch-run.js > scripts/ui/dispatch-run.js
```

There is no requirement to update every vault at once.

Vault A can use the latest config while Vault B keeps an older materialized version until you choose to refresh it.

This loose coupling is a feature.

---

## 11. Inspecting config before importing

You can inspect a file directly:

```bash
git show config/main:scripts/ui/dispatch-run.js
```

List a tree:

```bash
git ls-tree -r --name-only config/main
```

List only a subtree:

```bash
git ls-tree -r --name-only config/main scripts/ui
```

Compare the currently materialized local file with the config version:

```bash
git diff --no-index \
  scripts/ui/dispatch-run.js \
  <(git show config/main:scripts/ui/dispatch-run.js)
```

In zsh, process substitution (`<(...)`) makes this particularly convenient.

---

## 12. Pinning a specific config version

You do not have to import from `config/main`.

You can import from an exact commit:

```bash
git show 76ad192c3:scripts/ui/dispatch-run.js > scripts/ui/dispatch-run.js
```

Or from a tag:

```bash
git show config-v1.4:scripts/ui/dispatch-run.js > scripts/ui/dispatch-run.js
```

This matters for publishing/build reproducibility.

A project can say:

```text
content revision:  a8431c...
config revision:   76ad19...
```

and those two revisions together define the assembled environment.

---

## 13. Provenance without combining histories

If reproducibility matters, record the source config revision somewhere appropriate.

For example:

```bash
git rev-parse config/main
```

This returns the exact fetched commit.

A build manifest might contain:

```text
content_commit=a8431c...
config_commit=76ad192...
```

The repositories still remain independent.

This can later be automated by build scripts without changing the basic architecture.

---

## 14. Why not use submodules by default

A submodule represents another Git repository inside the working tree and stores a commit pointer to it.

That is useful when repository-level composition is genuinely required, but it adds lifecycle complexity:

- initialization;
- recursive cloning;
- detached HEAD behavior;
- explicit submodule revision management;
- additional failure modes when moving between machines.

For a handful of optional shared files, it solves a larger problem than necessary.

The selective materialization model is simpler.

---

## 15. Why not use Git subtree by default

`git subtree` is useful when an entire directory tree from another repository should be incorporated into the project and optionally synchronized upstream/downstream.

It is less attractive when shared files must land at unrelated locations such as:

```text
.obsidian/hotkeys.json
scripts/ui/...
templates/...
```

For scattered configuration paths, selective extraction is easier to reason about.

---

## 16. The resulting vault model

A vault can be created completely normally in Obsidian:

```text
1. Create native Obsidian vault
2. Install required plugins manually
3. git init
4. add `safety` remote
5. add `config` remote
6. git fetch config
7. materialize selected shared files
8. ignore config-owned paths
9. commit only vault-owned content/state
10. push vault commits to safety
```

No shared `_control` working tree is required merely to make vaults resemble one another.

The config repository is a **catalog/source of reusable files**, not a runtime dependency.

---

## 17. Droplet / publishing architecture

The same principle applies beyond Obsidian.

A server might contain several independent content projects:

```text
/srv/publishing/
├── hhp-book/
├── destination-yogyakarta/
├── client-site-a/
└── journal-site/
```

Each is its own content repository.

Each can fetch one or more shared sources:

```text
config       -> templates, CSS, common metadata
publishing   -> Typst/Pandoc machinery
web-tools    -> deployment/render scripts
```

For example:

```bash
git remote add config <config-url>
git fetch config

git show config/main:typst/book.typ > build/book.typ
git show config/main:css/article.css > public/css/article.css
```

The working tree then assembles:

```text
project content
+ shared template
+ common styling
+ shared build scripts
+ generated output
```

without forcing all of those components into one repository.

---

## 18. Publishing pipeline implications

This model naturally supports a modular pipeline:

```text
CONTENT REPO
manuscript / articles / metadata
       |
       +--------------------+
                            |
CONFIG REPO                 |
templates / CSS / layouts   |
       |                    |
       +----------+---------+
                  |
                  v
          ASSEMBLED WORK TREE
                  |
                  v
        Pandoc / Typst / scripts
                  |
                  v
        print / web / upload output
```

Other sources can be added later without changing the fundamental model.

For example:

```text
content repo
+ publication config repo
+ corporate style repo
+ website deployment repo
+ generated research/data
= assembled build environment
```

The important question for every path is simply:

> Which repository owns this file's history?

---

## 19. A useful future helper command

Once the manual process is familiar, it can be wrapped in a small script, for example:

```bash
vault-config update
```

Conceptually it would do only:

```bash
git fetch config

git show config/main:.obsidian/hotkeys.json > .obsidian/hotkeys.json
git show config/main:scripts/ui/plan-manager.js > scripts/ui/plan-manager.js
git show config/main:scripts/ui/dispatch-run.js > scripts/ui/dispatch-run.js
```

A publishing equivalent might be:

```bash
publication-config materialize
```

The helper should remain transparent: ordinary Git refs in, ordinary files out.

There is no need for a database or elaborate synchronization layer merely to distribute shared files.

---

## 20. Commands worth learning

These are the main Git primitives behind this architecture.

### Remotes

```bash
git remote -v
git remote add NAME URL
git remote remove NAME
```

### Fetch remote history without changing files

```bash
git fetch config
```

### Inspect refs

```bash
git branch -a
git log --oneline config/main -20
git rev-parse config/main
```

### List files in another revision

```bash
git ls-tree -r --name-only config/main
```

### Read one file from another revision

```bash
git show config/main:path/to/file
```

### Materialize it without local tracking

```bash
git show config/main:path/to/file > path/to/file
```

### Import and deliberately track it

```bash
git restore --source=config/main -- path/to/file
git add path/to/file
git commit
```

### See what the local repo actually owns

```bash
git ls-files
```

### See ignored files too

```bash
git status --ignored
```

These commands cover most of the proposed workflow.

---

## 21. Architectural rules of thumb

1. **Do not merge repositories merely because you need a file from another repository.**

2. **Treat `git fetch` as safe acquisition of history.** It updates remote-tracking refs but does not alter the working tree.

3. **Use `git show REF:path > file` when another repository owns the file.**

4. **Use `.gitignore` to keep externally owned materialized files out of the project's commits.**

5. **Use `git restore --source=...` plus a commit when intentionally vendoring a file.**

6. **Push only the project's own branch to its safety/content remote.**

7. **Do not `git pull` unrelated config history into the project branch.**

8. **Pin config commits/tags when exact build reproducibility matters.**

9. **Keep provenance explicit.** Content commit + config commit is often enough to reproduce an assembled environment.

10. **Add submodules/subtrees only when repository-level composition becomes a genuine requirement.**

---

## 22. Immediate AutoScribe decision

For now, one working vault is sufficient to finish and stabilize the AutoScribe pipeline.

There is no need to redesign the multi-vault architecture while pipeline behavior is still being ironed out.

The later vault architecture can use the model described here:

```text
native Obsidian vault
+ vault-specific safety Git history
+ selectively materialized shared config
```

That leaves the current implementation work focused on the pipeline rather than introducing another simultaneous architectural refactor.

