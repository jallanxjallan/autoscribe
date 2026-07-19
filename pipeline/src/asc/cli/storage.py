import json
from collections.abc import Iterable, Mapping
from typing import Any

import typer

from asc.ledger.inspect import (
    pending_export_for_source,
    pending_work,
    recent_calls,
    recent_exports,
    recent_results,
    recent_responses,
    show_call,
    show_response,
    table_counts,
)
from asc.ledger.lifecycle import (
    active_ledger_path,
    ensure_active_ledger,
    reset_ledger,
    rotate_ledger,
)
from asc.ledger.schema_dump import schema_columns, schema_sql

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Inspect and maintain the AutoScribe ledger.",
)


@app.command("path")
def path_command() -> None:
    """Print the active ledger path."""

    typer.echo(str(active_ledger_path()))


@app.command("init")
def init_command() -> None:
    """Create or update the active ledger schema."""

    path = ensure_active_ledger()
    typer.echo(f"initialized: {path}")


@app.command("reset")
def reset_command(
    yes: bool = typer.Option(False, "--yes", help="Reset without prompting."),
) -> None:
    """Drop and recreate all ledger objects."""

    ledger_path = active_ledger_path()
    if not yes:
        confirmed = typer.confirm(
            f"Reset the ledger and permanently delete all rows from {ledger_path}?"
        )
        if not confirmed:
            typer.echo("reset cancelled")
            raise typer.Exit()

    report = reset_ledger(apply=True)
    typer.echo(f"reset: {report.ledger_path}")


@app.command("rotate")
def rotate_command() -> None:
    """Archive the current ledger and create a fresh active ledger.

    Pending export custody rows are carried forward so completed-but-unexported
    work remains visible after rotation.
    """

    report = rotate_ledger()
    typer.echo(f"active:  {report.active_path}")
    if report.archive_path is not None:
        typer.echo(f"archive: {report.archive_path}")
    typer.echo(
        "carried: "
        f"calls={report.carried_calls} "
        f"responses={report.carried_responses} "
        f"exports={report.carried_exports}"
    )
    typer.echo(
        "removed from archive: "
        f"calls={report.old_deleted_calls} "
        f"responses={report.old_deleted_responses} "
        f"exports={report.old_deleted_exports}"
    )


@app.command("rotate-db")
def rotate_db_command() -> None:
    """Compatibility alias for ``rotate``."""

    rotate_command()


@app.command("schema")
def schema_command(
    columns: bool = typer.Option(False, "--columns", help="Print PRAGMA table_info rows instead of CREATE SQL."),
) -> None:
    """Print the actual active SQLite ledger schema."""

    if columns:
        rows = [
            (
                item.table,
                item.cid,
                item.name,
                item.column_type,
                item.not_null,
                item.default_value or "",
                item.primary_key,
            )
            for item in schema_columns()
        ]
        _print_table(("table", "cid", "name", "type", "not_null", "default", "pk"), rows)
        return

    for ddl in schema_sql():
        typer.echo(f"-- {ddl.name}")
        typer.echo(ddl.sql)
        typer.echo("")


@app.command("blocked")
def blocked_command(source_identity: str) -> None:
    """Check whether a source document has an unfinished export row."""

    row = pending_export_for_source(source_identity)
    if row is None:
        typer.echo(f"not blocked: {source_identity}")
        return
    _print_dict_rows([row], ("record_identity", "call_identity", "final_step", "result_key", "created_at"))


@app.command("counts")
def counts_command() -> None:
    """Print row counts for ledger tables."""

    rows = [(item.table, item.rows) for item in table_counts()]
    _print_table(("table", "rows"), rows)


@app.command("calls")
def calls_command(
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Print recent call rows."""

    rows = recent_calls(limit=limit)
    _print_dict_rows(
        rows,
        (
            "identity",
            "source_identity",
            "created_at",
            "response_status",
            "final_step",
            "result_key",
            "response_created_at",
            "exports",
        ),
    )


@app.command("responses")
def responses_command(
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="Maximum rows to print."),
    status: list[str] | None = typer.Option(None, "--status", "-s", help="Filter by success or failure."),
) -> None:
    """Print recent terminal response rows."""

    statuses = tuple(status or ())
    rows = recent_responses(limit=limit, statuses=statuses)
    _print_response_rows(rows)


@app.command("steps")
def steps_command(
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="Maximum rows to print."),
    status: list[str] | None = typer.Option(None, "--status", "-s", help="Filter by success or failure."),
) -> None:
    """Compatibility alias: print terminal responses, not intermediate steps."""

    statuses = tuple(status or ())
    rows = recent_responses(limit=limit, statuses=statuses)
    _print_response_rows(rows)


@app.command("exports")
def exports_command(
    limit: int = typer.Option(30, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Print recent export custody rows."""

    rows = recent_exports(limit=limit)
    _print_dict_rows(
        rows,
        (
            "export_id",
            "response_identity",
            "source_identity",
            "destination",
            "export_mode",
            "target_slug",
            "target_path",
            "exported_at",
            "export_message",
            "created_at",
        ),
    )


@app.command("results")
def results_command(
    limit: int = typer.Option(30, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Legacy alias: print recent terminal responses."""

    rows = recent_results(limit=limit)
    _print_response_rows(rows)


@app.command("pending")
def pending_command(
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Print failed responses plus pending exports."""

    rows = pending_work(limit=limit)
    _print_dict_rows(
        rows,
        (
            "identity",
            "record_identity",
            "source_identity",
            "call_identity",
            "final_step",
            "status",
            "result_key",
            "fail_message",
            "created_at",
        ),
    )


@app.command("show")
def show_command(identity: str) -> None:
    """Print one call with its terminal response and export rows as JSON."""

    try:
        data = show_call(identity)
    except KeyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    call_row = data.get("call", {})
    typer.echo(f"identity: {call_row.get('identity', '')}")
    typer.echo(f"source:   {call_row.get('source_identity', '')}")
    typer.echo(f"created:  {call_row.get('created_at', '')}")
    typer.echo("")
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("response")
def response_command(identity: str) -> None:
    """Print one terminal response as JSON."""

    try:
        data = show_response(identity)
    except KeyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("step")
def step_command(identity: str, step_number: int | None = None) -> None:
    """Compatibility alias: print the terminal response for a call identity.

    ``step_number`` is ignored because intermediate steps are no longer durable
    ledger rows.
    """

    try:
        data = show_response(identity)
    except KeyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _print_response_rows(rows: list[dict[str, Any]]) -> None:
    _print_dict_rows(
        rows,
        (
            "identity",
            "source_identity",
            "final_step",
            "status",
            "result_key",
            "fail_message",
            "created_at",
        ),
    )


def _print_dict_rows(rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]) -> None:
    materialized = [tuple(_cell(row.get(column, "")) for column in columns) for row in rows]
    _print_table(columns, materialized)


def _print_table(headers: tuple[str, ...], rows: Iterable[tuple[Any, ...]]) -> None:
    materialized = [tuple(_cell(cell) for cell in row) for row in rows]
    widths = [len(header) for header in headers]
    for row in materialized:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    typer.echo("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    typer.echo("  ".join("─" * width for width in widths))
    for row in materialized:
        typer.echo("  ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


if __name__ == "__main__":
    app()
