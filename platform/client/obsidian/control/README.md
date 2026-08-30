# AutoScribe Obsidian Control

Control is the Obsidian-facing UI. Git is the transport and provenance boundary for plans and instructions; the frontend does not use Redis or SQLite as configuration state.

## Plan Manager

`macros/plan-manager.js` builds its instruction catalogue from two Git-native sources:

- lightweight global instruction metadata fetched from the configured server catalogue ref (label/title, slug and brief description); and
- project-local instruction Markdown read from the current working tree.

When the same slug exists in both places, the local instruction wins. This makes a small project-specific variation of a global instruction an override rather than a second catalogue entry.

Plans live only on `refs/heads/autoscribe/config` as `plans/<slug>.json`; they are not working-tree files. Saving a plan snapshots the current local instructions as service-facing `instructions/<slug>.json` records on the same config ref, commits the new config snapshot, and pushes that ref. The server receive hook can then hand the pushed revision to `asc ingest`.

The default Git endpoints are:

- catalogue remote: `origin`
- catalogue ref: `refs/heads/autoscribe/catalog`
- config push remote: `origin`

They can be changed in `config/workflow.yaml`, by Git-facing deployment configuration, or with `AUTOSCRIBE_CATALOG_REMOTE`, `AUTOSCRIBE_CATALOG_REF`, and `AUTOSCRIBE_CONFIG_REMOTE`.

## Git ownership

The editorial/master branch is user-owned. Plan publication uses the machine-owned `refs/heads/autoscribe/config`; dispatch and response forensics use `refs/heads/autoscribe/inflight`.

## Write Responses

Write Responses first saves the response candidate on the inflight ref. A target is automatically writable only when master is clean and byte-identical to the source that was dispatched. Dirty or clean-but-diverged targets are reported as requiring a decision and are left untouched. A successful write is deliberately left dirty for editorial review.
