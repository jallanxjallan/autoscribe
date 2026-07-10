import sys

import click
from collections.abc import Iterable
from typing import Any, TextIO

import typer

from asc.exporter.export_result import (
    mark_result_exported,
    reset_result_exported,
    write_extracted_result_record,
    write_pending_result_records,
    write_result_record_by_slug,
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


@app.command("list-pending")
def list_pending(
    source_identity: str | None = typer.Argument(
        None,
        help=(
            "Optional source/record identity. With no argument, print a table. "
            "With an identity, emit matching pending source identities for writeback."
        ),
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


@app.command("extract-pending")
def extract_pending_results() -> None:
    """Emit all pending extracted call/result rows as an NDJSON batch."""

    with connect() as conn:
        write_pending_result_records(conn=conn, sink=sys.stdout)


@app.command("re-export")
def re_export(
    slug: str = typer.Argument(
        ...,
        help="Source slug to emit again as NDJSON.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation before emitting overwrite-oriented NDJSON.",
    ),
    export_message: str = typer.Option(
        "re-export",
        "--export-message",
        "--message",
        help="Message to store in the exports row.",
    ),
) -> None:
    """Emit one slug's latest result as NDJSON and record a fresh export receipt."""

    cleaned = slug.strip()
    if not cleaned:
        typer.echo("ERROR: slug must not be empty", err=True)
        raise typer.Exit(code=1)

    if not yes:
        confirmed = click.confirm(
            f"Re-export {cleaned!r}? This is intended to overwrite a dirty writeback file.",
            default=False,
            err=True,
        )
        if not confirmed:
            typer.echo("re-export=cancelled", err=True)
            raise typer.Exit(code=1)

    try:
        with connect() as conn:
            write_result_record_by_slug(
                slug=cleaned,
                conn=conn,
                sink=sys.stdout,
                export_message=export_message,
            )
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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
    """Delete export receipts for the supplied identities, making responses pending again."""

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
