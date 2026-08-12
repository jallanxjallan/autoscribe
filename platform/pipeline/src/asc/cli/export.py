import json
import sys

from collections.abc import Iterable
from typing import Any, TextIO

import typer

from asc.exporter.export_result import (
    mark_result_exported,
    reset_result_exported,
    write_pending_result_records,
    write_result_records_by_slugs,
)
from asc.exporter.pending_exports import pending_export_records
from asc.ledger.connect import connect

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
    headers = (
        "slug",
        "source_identity",
        "call_identity",
        "final_step",
        "result_key",
        "exported_at",
    )
    table_rows = [
        tuple(
            _text(row.get("exported_at_text") if header == "exported_at" else row.get(header, ""))
            for header in headers
        )
        for row in rows
    ]

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



def _write_pending_exports_ndjson(
    *,
    rows: list[dict[str, object]],
    sink: TextIO,
) -> None:
    """Emit lightweight pending-export metadata as one JSON object per line."""

    for row in rows:
        payload = {
            "slug": row.get("slug"),
            "source_identity": row.get("source_identity") or row.get("record_identity"),
            "record_identity": row.get("record_identity") or row.get("source_identity"),
            "call_identity": row.get("call_identity"),
            "final_step": row.get("final_step"),
            "result_key": row.get("result_key"),
            "result_identity": row.get("result_identity") or row.get("call_identity"),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sink)


@app.command("list-pending")
def list_pending(
    source_identity: str | None = typer.Argument(
        None,
        help=(
            "Optional source/record identity. With no argument, print a table. "
            "With an identity, emit matching pending source identities for writeback."
        ),
    ),
    ndjson: bool = typer.Option(
        False,
        "--ndjson",
        "--json",
        help="Emit pending-export metadata as NDJSON instead of a display table.",
    ),
) -> None:
    """List pending export/writeback rows by slug and identity."""

    if source_identity is not None:
        source_identity = source_identity.strip()
        if not source_identity:
            typer.echo("ERROR: source identity must not be empty", err=True)
            raise typer.Exit(code=1)

    with connect() as conn:
        rows = pending_export_records(conn=conn, source_identity=source_identity)

    if ndjson:
        _write_pending_exports_ndjson(rows=rows, sink=sys.stdout)
    elif source_identity is None:
        _write_pending_exports_table(rows=rows, sink=sys.stdout)
    else:
        _write_source_identity_stream(rows=rows, sink=sys.stdout)


@app.command("extract-selected")
def extract_selected(
    slugs: list[str] = typer.Argument(
        ...,
        help="Source slugs whose latest completed results should be retrieved.",
    ),
    export_message: str = typer.Option(
        "retrieve-results",
        "--export-message",
        "--message",
        help="Message to store in each export receipt.",
    ),
) -> None:
    """Emit available results by slug and append export receipts."""

    cleaned = [slug.strip() for slug in slugs if slug.strip()]
    if not cleaned:
        typer.echo("ERROR: at least one source slug is required", err=True)
        raise typer.Exit(code=1)

    try:
        with connect() as conn:
            missing = write_result_records_by_slugs(
                slugs=cleaned,
                conn=conn,
                sink=sys.stdout,
                export_message=export_message,
            )
        for slug in missing:
            typer.echo(f"No completed result for source slug: {slug}", err=True)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("extract-pending")
def extract_pending_results() -> None:
    """Emit all pending extracted call/result rows as an NDJSON batch."""

    with connect() as conn:
        write_pending_result_records(conn=conn, sink=sys.stdout)


@app.command("update-exports")
def update_exports(
    result_identity: str = typer.Argument(
        ...,
        help="Call identity or full terminal result key that was successfully exported.",
    ),
    export_message: str = typer.Option(
        "writeback",
        "--export-message",
        "--message",
        help="Message to store in the exports row.",
    ),
) -> None:
    """Record an export receipt after successful client-side writeback."""

    with connect() as conn:
        mark_result_exported(
            result_identity=result_identity,
            conn=conn,
            export_message=export_message,
        )


@app.command("reset-exports")
def reset_exports(
    identities: list[str] = typer.Argument(
        ...,
        help="Call, result-key, response, or source identities to mark pending again.",
    ),
    export_message: str = typer.Option(
        "reset",
        "--export-message",
        "--message",
        help="Ignored under the receipt-table model; retained for CLI compatibility.",
    ),
) -> None:
    """Delete export receipts for the supplied identities, making results pending again."""

    cleaned = [identity.strip() for identity in identities if identity.strip()]
    if not cleaned:
        typer.echo("ERROR: at least one identity is required", err=True)
        raise typer.Exit(code=1)

    with connect() as conn:
        count = reset_result_exported(
            identities=cleaned,
            conn=conn,
            export_message=export_message,
        )
    typer.echo(f"Reset {count} export receipt(s).")


def _write_table(headers: Iterable[str], rows: Iterable[Iterable[str]], *, sink: TextIO) -> None:
    header_values = tuple(headers)
    row_values = [tuple(row) for row in rows]
    widths = [len(header) for header in header_values]
    for row in row_values:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(header_values)), file=sink)
    print("  ".join("─" * width for width in widths), file=sink)
    for row in row_values:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(header_values))), file=sink)


if __name__ == "__main__":
    app()
