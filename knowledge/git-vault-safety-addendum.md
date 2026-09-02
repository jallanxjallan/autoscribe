# Git Vault Safety Addendum

## Purpose

This note supplements the earlier Git working-tree assembly reference. It records the final decision for **content safety and version restoration** across multiple Obsidian vaults.

The GitHub repository is **not part of the live AutoScribe pipeline**. It exists only as a remote safety copy of each vault's durable, human-facing `master` history.

## Final Repository Model

Each Obsidian vault remains its own fully independent local Git repository.

Example:

```text
HHPLawFirm/
├── .git/
├── master
├── AutoScribe operational refs/branches
└── vault content
```

Another vault has a completely separate `.git` directory, index, locks, refs, working tree, and history.

This preserves the isolation needed when both Obsidian and the Rust service are reading from and operating around the vault repository.

## One GitHub Repository, One Branch per Vault

Instead of creating a separate GitHub repository for every vault, use one GitHub repository as a branch namespace for safety copies.

Example remote repository:

```text
vault-safety.git
├── vault-hhp
├── vault-jogja
├── vault-autoscribe-alpha
└── ...
```

These branches do **not** need related histories. Git allows unrelated histories to coexist as separate branches in the same repository.

Each local vault pushes only its own `master` branch to its assigned remote branch.

For example, from the HHP vault:

```bash
git remote add github git@github.com:USER/vault-safety.git
git push github master:vault-hhp
```

From another vault:

```bash
git push github master:vault-jogja
```

The remote branch name is only a storage namespace. It does not need to carry pipeline semantics.

## AutoScribe Boundary

The current architectural assumption is:

- the Rust daemon may read from `master`;
- the Rust daemon does **not** write to `master`;
- AutoScribe operational state may use other local refs or branches;
- the deliberate overwrite/update of `master` is handled by the Obsidian-side script;
- therefore only `master` needs to be replicated to GitHub for safety.

GitHub should not receive AutoScribe's transient or operational refs.

Conceptually:

```text
local vault repo
├── master                    -> pushed to GitHub
├── autoscribe/...            -> local only
├── transient refs            -> local only
└── other operational state   -> local only
```

Remote:

```text
GitHub vault-safety.git
└── vault-hhp                 <- local master only
```

## Make the Push Mapping Explicit

Configure each vault so that a normal push to the GitHub safety remote sends exactly one ref.

Example for HHP:

```bash
git remote add github git@github.com:USER/vault-safety.git

git config remote.github.push \
  refs/heads/master:refs/heads/vault-hhp
```

Then:

```bash
git push github
```

pushes only:

```text
local master -> remote vault-hhp
```

This reduces the chance of accidentally publishing AutoScribe operational branches.

For another vault:

```bash
git config remote.github.push \
  refs/heads/master:refs/heads/vault-jogja
```

## Commands to Avoid

Do not use broad push operations against the shared GitHub safety repository:

```bash
git push --all github
```

and especially:

```bash
git push --mirror github
```

Those can publish refs that are intended to remain local.

The desired rule is intentionally narrow:

> Only the durable `master` history is copied to GitHub.

## Restoring a Vault on Another Machine

A machine that needs only one vault can clone just that branch:

```bash
git clone \
  --single-branch \
  --branch vault-hhp \
  git@github.com:USER/vault-safety.git \
  HHPLawFirm
```

The checked-out branch will initially be named `vault-hhp`. If the local convention requires `master`, rename it:

```bash
cd HHPLawFirm
git branch -m master
```

The GitHub branch remains `vault-hhp`; the local branch may still be called `master`.

Set the safety push mapping again:

```bash
git config remote.origin.push \
  refs/heads/master:refs/heads/vault-hhp
```

Or rename the remote from `origin` to `github` if preferred:

```bash
git remote rename origin github
git config remote.github.push \
  refs/heads/master:refs/heads/vault-hhp
```

## Separation of Responsibilities

The resulting safety architecture has several independent layers:

```text
Local vault Git
    |
    | master only
    v
GitHub shared safety repo
    one branch per vault

Local filesystem
    |
    v
restic backup

Optional Git bundles / archives
    |
    v
Google Drive or Dropbox
```

Responsibilities:

### Local Git

- normal version history;
- diffs and restoration;
- AutoScribe's local Git-based operations;
- operational refs remain available locally.

### GitHub

- off-machine copy of durable vault content history;
- one branch per vault;
- restoration source if the local repository is lost;
- not used for runtime coordination.

### restic

- machine/filesystem backup;
- can protect the entire local repository, including refs that are intentionally not pushed to GitHub.

### Google Drive / Dropbox

Use for cold backup artifacts such as Git bundles, archives, exports, PDFs, and similar ordinary files.

Avoid using cloud-sync folders as the live storage location for active bare Git repositories.

## Why Not a Shared Working-Tree Monorepo

A single Git working tree containing all vaults was rejected.

Although technically possible, it would cause every vault to share:

- one Git index;
- one lock namespace;
- one branch state;
- one repository-wide status;
- one failure/corruption domain.

That is undesirable when Obsidian and Rust processes can both be active around different vaults.

The selected architecture retains:

```text
one vault = one working tree = one local Git repository
```

while centralizing only the remote safety copies.

## Why the Branch-per-Vault Remote Works

Branches in Git are refs to commits. Separate branches in the same remote repository are not required to share ancestry.

Therefore:

```text
vault-hhp
vault-jogja
vault-project-x
```

can each represent a completely unrelated local repository history.

This gives the administrative convenience of one GitHub repository without merging or coupling the local vault repositories.

## Access-Control Tradeoff

A shared GitHub repository has repository-wide access by default.

Someone who can read the repository can generally read all vault branches.

If a particular vault later needs different collaborator access, that vault can be moved to its own remote repository without changing the local one-vault-one-repo architecture.

## Working Principle

The final rule is:

> Each vault owns its own local Git repository. AutoScribe operational refs stay local. GitHub receives only the vault's durable `master` history, stored under a vault-specific branch in one shared safety repository.

This keeps runtime mechanics local and isolated while making off-machine content recovery simple.
