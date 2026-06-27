import sys
from collections.abc import Iterable, Mapping
from typing import Any, TextIO

import typer

from asc.exporter.export_result import mark_result_exported, write_extracted_result_record
from asc.exporter.pending_exports import pending_export_records
from asc.scrivener.connect import connect

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Export and write back completed ledger results.",
)


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _write_pending_exports_table(
    *,
    rows: list[dict[str, object]],
    sink: TextIO,
) -> None:
    headers = ("source_identity", "call_identity", "final_step", "result_key")
    table_rows = [tuple(_text(row.get(header, "")) for header in headers) for row in rows]

    if not table_rows:
        print("No pending exports.", file=sink)
        return

    _write_table(headers, table_rows, sink=sink)


def _write_source_identity_stream(
    *,
    rows: list[dict[str, object]],
    sink: TextIO,
) -> None:
    for row in rows:
        print(_text(row.get("source_identity") or row.get("record_identity")), file=sink)


@app.command("list-pending-exports")
def list_pending_exports(
    source_identity: str | None = typer.Argument(
        None,
        help=(
            "Optional source/record identity. With no argument, print a table. "
            "With an identity, emit matching pending source identities for writeback."
        ),
    ),
) -> None:
    """List pending export/writeback rows."""

    if source_identity is not None:
        source_identity = source_identity.strip()
        if not source_identity:
            typer.echo("ERROR: source identity must not be empty", err=True)
            raise typer.Exit(code=1)

    with connect() as conn:
        rows = pending_export_records(conn=conn, source_identity=source_identity)

    if source_identity is None:
        _write_pending_exports_table(rows=rows, sink=sys.stdout)
    else:
        _write_source_identity_stream(rows=rows, sink=sys.stdout)


@app.command("extract-result")
def extract_result(
    call_identity: str = typer.Argument(
        ...,
        help="Call identity to extract from the ledger.",
    ),
) -> None:
    """Emit one extracted call/result row as NDJSON."""

    with connect() as conn:
        write_extracted_result_record(
            call_identity=call_identity,
            conn=conn,
            sink=sys.stdout,
        )


@app.command("update-exports")
def update_exports(
    result_identity: str = typer.Argument(
        ...,
        help="Result key, result identity, or call identity that was successfully exported.",
    ),
    export_message: str = typer.Option(
        "writeback",
        "--export-message",
        "--message",
        help="Message to store in the exports row.",
    ),
) -> None:
    """Mark one result as exported after successful client-side writeback."""

    with connect() as conn:
        mark_result_exported(
            result_identity=result_identity,
            conn=conn,
            export_message=export_message,
        )


def _write_table(
    headers: tuple[str, ...],
    rows: Iterable[tuple[Any, ...]],
    *,
    sink: TextIO,
) -> None:
    materialized = [tuple(_text(cell) for cell in row) for row in rows]
    widths = [len(header) for header in headers]
    for row in materialized:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)), file=sink)
    print("  ".join("─" * width for width in widths), file=sink)
    for row in materialized:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(headers))), file=sink)


if __name__ == "__main__":
    app()
