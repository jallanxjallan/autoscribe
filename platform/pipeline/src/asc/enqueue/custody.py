"""Guard source documents that still have completed work awaiting writeback."""

from __future__ import annotations

from asc.ledger.inspect import pending_export_for_source


class PendingExportError(ValueError):
    """Raised when a source already has a completed response awaiting export."""


def ensure_no_pending_export(source_identity: str) -> None:
    """Reject enqueue while the source remains in pending-export custody.

    Export receipts are the authoritative acknowledgement that completed work
    has been written back. Until that receipt exists, another call for the same
    source would risk producing a second result against stale source content.
    """

    identity = str(source_identity).strip()
    if not identity:
        raise ValueError("source_identity must be a non-empty string")

    pending = pending_export_for_source(identity)
    if pending:
        raise PendingExportError(
            f"source has a completed response pending export: {identity}"
        )


__all__ = ["PendingExportError", "ensure_no_pending_export"]
