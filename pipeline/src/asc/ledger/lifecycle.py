from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from asc.ledger.connect import configured_ledger_path, connect
from asc.ledger.schema import ensure_ledger_schema, reset_ledger_schema


DEFAULT_ARCHIVE_DIRNAME = "archive"
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


@dataclass(frozen=True, slots=True)
class ResetReport:
    ledger_path: Path
    applied: bool


@dataclass(frozen=True, slots=True)
class RotateReport:
    active_path: Path
    archive_path: Path | None
    carried_calls: int
    carried_responses: int
    carried_exports: int
    old_deleted_calls: int
    old_deleted_responses: int
    old_deleted_exports: int


def timestamp_label() -> str:
    return datetime.now(JAKARTA_TZ).strftime("%Y%m%dT%H%M%S%z")


def active_ledger_path() -> Path:
    return configured_ledger_path().expanduser().resolve()


def archive_path_for(ledger_path: Path, archive_dir: Path | None = None) -> Path:
    archive_root = archive_dir.expanduser().resolve() if archive_dir else ledger_path.parent / DEFAULT_ARCHIVE_DIRNAME
    suffix = ledger_path.suffix or ".sqlite"
    return archive_root / f"{ledger_path.stem}.{timestamp_label()}{suffix}"


def ensure_active_ledger() -> Path:
    with connect() as conn:
        ensure_ledger_schema(conn)
    return active_ledger_path()


def reset_ledger(*, apply: bool = False) -> ResetReport:
    ledger_path = active_ledger_path()
    if not apply:
        return ResetReport(ledger_path=ledger_path, applied=False)
    with connect() as conn:
        reset_ledger_schema(conn)
    return ResetReport(ledger_path=ledger_path, applied=True)


def rotate_ledger(*, archive_dir: Path | None = None) -> RotateReport:
    active_path = active_ledger_path()

    if not active_path.exists():
        initialized = ensure_active_ledger()
        return RotateReport(
            active_path=initialized,
            archive_path=None,
            carried_calls=0,
            carried_responses=0,
            carried_exports=0,
            old_deleted_calls=0,
            old_deleted_responses=0,
            old_deleted_exports=0,
        )

    target_archive = archive_path_for(active_path, archive_dir=archive_dir)
    target_archive.parent.mkdir(parents=True, exist_ok=True)
    if target_archive.exists():
        raise FileExistsError(f"archive target already exists: {target_archive}")

    active_path.rename(target_archive)
    try:
        ensure_active_ledger()
        report_counts = _carry_unexported_rows(
            archived_path=target_archive,
            new_active_path=active_path,
        )
    except Exception:
        if active_path.exists():
            active_path.unlink()
        target_archive.rename(active_path)
        raise

    return RotateReport(active_path=active_path, archive_path=target_archive, **report_counts)


def _carry_unexported_rows(*, archived_path: Path, new_active_path: Path) -> dict[str, int]:
    old = sqlite3.connect(str(archived_path))
    new = sqlite3.connect(str(new_active_path))
    old.row_factory = sqlite3.Row
    new.row_factory = sqlite3.Row
    old.execute("PRAGMA foreign_keys = ON")
    new.execute("PRAGMA foreign_keys = ON")

    try:
        identities = _unexported_response_identities(old)
        if not identities:
            old.commit()
            new.commit()
            return _zero_counts()

        carried_calls = _copy_rows(old, new, table="calls", where=f"identity IN ({_placeholders(identities)})", params=identities)
        carried_responses = _copy_rows(old, new, table="responses", where=f"identity IN ({_placeholders(identities)})", params=identities)
        carried_exports = _copy_rows(old, new, table="exports", where=f"response_identity IN ({_placeholders(identities)})", params=identities)
        new.commit()

        old_deleted_exports = _delete_rows(old, table="exports", where=f"response_identity IN ({_placeholders(identities)})", params=identities)
        old_deleted_responses = _delete_rows(old, table="responses", where=f"identity IN ({_placeholders(identities)})", params=identities)
        old_deleted_calls = _delete_rows(old, table="calls", where=f"identity IN ({_placeholders(identities)})", params=identities)
        old.commit()

        return {
            "carried_calls": carried_calls,
            "carried_responses": carried_responses,
            "carried_exports": carried_exports,
            "old_deleted_calls": old_deleted_calls,
            "old_deleted_responses": old_deleted_responses,
            "old_deleted_exports": old_deleted_exports,
        }
    except Exception:
        old.rollback()
        new.rollback()
        raise
    finally:
        old.close()
        new.close()


def _unexported_response_identities(conn: sqlite3.Connection) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT r.identity
        FROM responses AS r
        LEFT JOIN exports AS e
            ON e.response_identity = r.identity
        WHERE r.status = 'success'
          AND e.response_identity IS NULL
        ORDER BY r.identity ASC
        """
    ).fetchall()
    return tuple(str(row["identity"]) for row in rows)


def _copy_rows(old: sqlite3.Connection, new: sqlite3.Connection, *, table: str, where: str, params: tuple[str, ...]) -> int:
    rows = old.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()
    if not rows:
        return 0

    columns = tuple(rows[0].keys())
    values = [tuple(row[col] for col in columns) for row in rows]
    col_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    new.executemany(f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})", values)
    return len(rows)


def _delete_rows(conn: sqlite3.Connection, *, table: str, where: str, params: tuple[str, ...]) -> int:
    cursor = conn.execute(f"DELETE FROM {table} WHERE {where}", params)
    return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _placeholders(values: tuple[str, ...]) -> str:
    if not values:
        raise ValueError("cannot render placeholders for an empty value set")
    return ", ".join("?" for _ in values)


def _zero_counts() -> dict[str, int]:
    return {
        "carried_calls": 0,
        "carried_responses": 0,
        "carried_exports": 0,
        "old_deleted_calls": 0,
        "old_deleted_responses": 0,
        "old_deleted_exports": 0,
    }


__all__ = [
    "RotateReport",
    "ResetReport",
    "active_ledger_path",
    "archive_path_for",
    "ensure_active_ledger",
    "reset_ledger",
    "rotate_ledger",
    "timestamp_label",
]
