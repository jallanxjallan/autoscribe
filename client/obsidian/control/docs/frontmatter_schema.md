# Frontmatter Schema

## Required Fields

- `slug`: immutable identity for every slugged editorial record.
- `action`: the next editorial action. It must always be present. Use `defer` when no immediate work is required.
- `class`

## Machine-Owned Pipeline Metadata

Successful AI response acceptance writes:

```yaml
pipeline:
  run: run.20260801T041105.a82c
  plan: plan.cleanup-final
  written_at: 2026-08-01T04:11:05+07:00
action: review
```

All AI-generated or AI-revised content must be reviewed. Dispatch removes the previous `pipeline` object before creating the source snapshot, but never removes `action`. Git remains authoritative for transport and decision history; `pipeline` exists to group and review the current writeback run in Bases.

## Common Optional Fields

- `context`
- `content_kind`
- `project`
- `stage`
- `status`

## Guidance

- `project`: optional grouping key for editorial work.
- `stage`: optional editorial stage such as `draft`, `revise`, or `final`.
- `class`: authored note class such as `content`, `instruction`, or `topic`.
- `content_kind`: optional subtype metadata for content notes, for example `passage`, `excerpt`, or `image-note`.
- `status`: optional descriptive workflow marker for inspection.
- `action`: required operational instruction such as `review`, `rewrite`, `research`, `submit`, or `defer`.

## Principle

Git records what happened. Frontmatter describes what the editor should do next and identifies the current pipeline writeback batch.
