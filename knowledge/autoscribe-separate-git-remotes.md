# Separate Git Remotes for AutoScribe Publication

## Recommended model

Maintain two explicitly named Git remotes with distinct roles:

```bash
git remote add pipeline <pipeline-repo-url>
git remote add archive  git@github.com:jallanxjallan/<repo>.git
```

Use:

- `pipeline` — operational publication remote consumed by AutoScribe.
- `archive` — durable GitHub mirror/backup alongside the other pipeline code.

Avoid treating both destinations as one logical remote.

## Default push target

Make the operational pipeline remote the default push destination:

```bash
git config remote.pushDefault pipeline
```

Then a normal:

```bash
git push
```

means “publish to AutoScribe.”

## Publish explicitly to both remotes

The compilation/publication workflow should perform two separate pushes:

```bash
git push pipeline master
git push archive master
```

If plans live on another branch/ref, push the same refs to both:

```bash
git push pipeline     master     autoscribe/plans

git push archive     master     autoscribe/plans
```

## Do not use multiple push URLs for one remote

Git supports configuring one remote with several `pushurl` values, but that is not ideal here.

Pipeline publication and archival are operationally different events. They should be independently observable because either may fail while the other succeeds.

For example:

```text
Compile        ✓
Pipeline push  ✓  commit 8ac27df
Archive push   ✗  network timeout

Published operationally; archival retry required.
```

Pipeline success determines whether the new Control state is operational.

Archive success determines whether the publication has been safely mirrored.

An archival failure should not block normal pipeline operation.

## Push identical Git objects

Compile and validate once, commit once, then push that exact commit to both destinations.

```text
edit source
   ↓
compile / validate
   ↓
commit published state
   ↓
       same Git objects
      /                \
pipeline              archive
```

This allows a simple integrity check:

```text
pipeline/master == archive/master == local published commit
```

Do not independently recompile for each remote.

## Fetch policy

Treat the archive as primarily push-only.

If reconciliation requires fetching, fetch from the operational/authoritative remote, normally `pipeline`:

```bash
git config remote.pipeline.fetch '+refs/heads/*:refs/remotes/pipeline/*'
```

There is normally no reason for AutoScribe to pull state back from GitHub merely because GitHub stores the archive.

## Naming convention

Prefer descriptive remote names and omit `origin`:

```text
pipeline    — operational publication
archive     — GitHub historical mirror
```

Using `origin` would introduce an unnecessary implicit “main remote” concept when the repository genuinely has two destinations with different purposes.

## Architectural rule

**Compile once, commit once, publish the same commit to two independently tracked remotes.**

The publisher should record pipeline and archive outcomes separately and allow archival failures to be retried without affecting successful operational publication.
