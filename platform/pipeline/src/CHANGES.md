# Publication-domain removal

- Plans now use deterministic SHA-256 identities derived from their slug and canonical content.
- Instructions now use deterministic SHA-256 identities derived from their slug and normalized content.
- Upload no longer requires `publication_ulid`.
- Enqueue resolves the current plan and instruction record directly through `state:slugmap:index`.
- `asc/state/publications.py` is removed by `install.sh`.
- Timestamps remain ordinary upload metadata rather than part of record identity.
