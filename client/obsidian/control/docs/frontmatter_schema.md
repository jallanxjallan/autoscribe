# Frontmatter Schema

## Minimum For Canonical Note Creation

- `class`

## Common Optional Fields In Created Notes

- `context`
- `content_kind`
- `project`
- `stage`
- `status`
- `slug`

## Guidance

- `slug`: leave blank in slugged note templates and let the embedded runtime fill it; topic notes do not use a slug.
- `project`: optional grouping key for editorial work.
- `stage`: optional editorial stage such as `draft`, `revise`, or `final`.
- `class`: optional authored note class such as `content`, `instruction`, or `topic`.
- `content_kind`: optional subtype metadata for content notes, for example `passage`, `excerpt`, or `image-note`.
- `status`: optional workflow marker for inspection only.

## Principle

Active templates should not hardcode frontmatter values. The active `content` template keeps a minimal scaffold and the embedded create-note runtime or `wkb writenew` fills additional metadata such as `project`, `context`, and `content_kind` at creation time.
