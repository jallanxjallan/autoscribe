from asc.ledger.connect import connect
from asc.ledger.queries import (
    SELECT_CALL_SQL,
    SELECT_CALLS_SQL,
    SELECT_RESPONSE_SQL,
    SELECT_RESPONSES_SQL,
)
from asc.ledger.schema import drop_user_objects, ensure_ledger_schema
from asc.ledger.util import fetch_all_dicts, fetch_one_dict


def init_database(*, force: bool = False) -> None:
    """Initialize the active SQLite ledger database."""

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


def read_response(call_identity: str) -> dict[str, object] | None:
    with connect() as conn:
        return fetch_one_dict(conn, SELECT_RESPONSE_SQL, (call_identity,))


def read_responses() -> list[dict[str, object]]:
    with connect() as conn:
        return fetch_all_dicts(conn, SELECT_RESPONSES_SQL)


__all__ = [
    "init_database",
    "read_call",
    "read_calls",
    "read_response",
    "read_responses",
]
