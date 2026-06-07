from __future__ import annotations

from asc.ledger.connect import connect
from asc.ledger.schema import drop_user_objects, ensure_ledger_schema


def init_database(*, force: bool = False) -> None:
    """
    Initialize SQLite persistence schema.

    force=False ensures the schema exists without deleting data.
    force=True drops all user-defined ledger objects and recreates the schema.
    """

    with connect() as conn:
        if force:
            drop_user_objects(conn)
        ensure_ledger_schema(conn)


__all__ = ["init_database"]
