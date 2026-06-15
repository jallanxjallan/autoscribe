from __future__ import annotations

import sys
from typing import TextIO

import typer

from asc.export.export_result import mark_result_exported, write_extracted_result_record
from asc.export.pending_exports import pending_export_records
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
    headers = ("prompt_slug", "call_identity", "result_identity")
    table_rows = [
        (
            _text(row["prompt_slug"]),
            _text(row["call_identity"]),
            _text(row["result_identity"]),
        )
        for row in rows
    ]

    if not table_rows:
        print("No pending exports.", file=sink)
        return

    widths = tuple(
        max(len(header), *(len(row[index]) for row in table_rows))
        for index, header in enumerate(headers)
    )

    print(
        f"{headers[0]:<{widths[0]}}  {headers[1]:<{widths[1]}}  {headers[2]:<{widths[2]}}",
        file=sink,
    )
    print(
        f"{'-' * widths[0]}  {'-' * widths[1]}  {'-' * widths[2]}",
        file=sink,
    )

    for prompt_slug, call_identity, result_identity in table_rows:
        print(
            f"{prompt_slug:<{widths[0]}}  {call_identity:<{widths[1]}}  {result_identity:<{widths[2]}}",
            file=sink,
        )


def _write_prompt_slug_stream(
    *,
    rows: list[dict[str, object]],
    sink: TextIO,
) -> None:
    for row in rows:
        print(_text(row["prompt_slug"]), file=sink)


@app.command("list-pending-exports")
def list_pending_exports(
    plan_slug: str | None = typer.Argument(
        None,
        help=(
            "Optional plan slug. With no argument, print a human-readable table. "
            "With a plan slug, emit one pending prompt slug per line for writeback."
        ),
    ),
) -> None:
    """List pending export/writeback rows.

    Pending-export custody and duplicate-slug checks are owned by asc.ledger.
    This command only chooses a display format and applies the optional plan
    filter through the export helper.
    """

    if plan_slug is not None:
        plan_slug = plan_slug.strip()
        if not plan_slug:
            typer.echo("ERROR: plan slug must not be empty", err=True)
            raise typer.Exit(code=1)

    with connect() as conn:
        rows = pending_export_records(conn=conn, plan_slug=plan_slug)

    if plan_slug is None:
        _write_pending_exports_table(rows=rows, sink=sys.stdout)
    else:
        _write_prompt_slug_stream(rows=rows, sink=sys.stdout)


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
        help="Result identity that was successfully exported or written back.",
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


if __name__ == "__main__":
    app()
