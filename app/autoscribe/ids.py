"""Opaque identities for new submission operations."""

def new_submission_id() -> str:
    """Allocate once for a new operation; transports must retain it for retries."""
    import uuid
    return str(uuid.uuid4())


def validate_submission_id(value: object) -> str:
    """Require canonical lowercase RFC 4122 UUIDv4, without semantic prefixes."""
    import uuid
    if not isinstance(value, str):
        raise ValueError('submission_id must be a canonical UUIDv4')
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError('submission_id must be a canonical UUIDv4') from exc
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122 or str(parsed) != value:
        raise ValueError('submission_id must be a canonical UUIDv4')
    return value
