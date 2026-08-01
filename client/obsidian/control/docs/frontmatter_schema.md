# Frontmatter Schema

Frontmatter describes the editorial record and what should happen next. Git, transport branches, decision tags, manifests, and ledgers describe what happened operationally. Pipeline state is reconstructed in the File State panel and is not stored in frontmatter.

## Design principle

Stable identity is separated from mutable use or treatment:

- `record` → `component`
- `origin` → `producer`

## Required common fields

- `slug`: immutable record identity. Its prefix should agree with `record`.
- `record`: intrinsic record type.
- `component`: current editorial function.
- `action`: next operation. AI actions use actor-qualified values such as `ai-draft`, `ai-revise`, and `ai-proofread`. Successful response writeback sets `human-review`.
- `scope`: canonical structural or project home.
- `origin`: original source or producer.
- `producer`: producer of the current version.

## Editorial content fields

Content and material records may also use:

- `stage`: broad production phase.
- `status`: current editorial condition; approval is not encoded here.
- `position`: quoted ordering code within the scalar `scope`.
- `topic`: permanent topic wikilinks; always list-valued.
- `source`: permanent source wikilinks; always list-valued.
- `claims`: permanent claim wikilinks where applicable; always list-valued.

Instruction records do not require `stage`, `status`, or `position`.

## Pipeline rule

Dispatch Run compares each selected file's `action` with the selected plan's machine-readable `type`. A mismatch raises a warning but may be overridden deliberately.

Write Responses preserves the source frontmatter, replaces only the body, removes any legacy `pipeline` mapping, and sets:

```yaml
action: human-review
```

The File State panel derives per-file pipeline status from Git and retained transport records.
