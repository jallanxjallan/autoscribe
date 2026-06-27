from asc.ledger.connect import connect
from asc.ledger.queries import SELECT_CALL_SQL, SELECT_CALLS_SQL
from asc.ledger.schema import drop_user_objects, ensure_ledger_schema
from asc.ledger.util import fetch_all_dicts, fetch_one_dict


def init_database(*, force: bool = False) -> None:
    """Initialize the active SQLite ledger database.

    This is intentionally small because Scrivener is not the workflow owner.
    ``force=True`` drops user ledger objects first; otherwise this only ensures
    the schema exists.
    """

    with connect() as conn:
        if force:
            drop_user_objects(conn)
        ensure_ledger_schema(conn)


def read_call(call_identity: str) -> dict[str, object] | None:
    with connect() as conn:
        return fetch_one_dict(conn, SELECT_CALL_SQL, (call_identity,))


def read_calls() -> list[dict[str, object]]:
    with connect() as conn:
        return fetch_all_dicts(conn, SELECT_CALLS_SQL)


__all__ = ["init_database", "read_call", "read_calls"]
