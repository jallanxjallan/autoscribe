from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from typing import Any

import typer

from asc.scrivener.inspect import (
    pending_work,
    recent_calls,
    recent_exports,
    recent_results,
    recent_steps,
    show_call,
    show_step,
    table_counts,
)

app = typer.Typer(help="Inspect the Scrivener ledger.")


@app.command("counts")
def counts_command() -> None:
    """Print row counts for ledger tables."""

    rows = [(item.table, item.rows) for item in table_counts()]
    _print_table(("table", "rows"), rows)


@app.command("calls")
def calls_command(
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Print recent call rows.

    The ledger no longer owns workflow state.  It records calls, completed or
    failed steps, and export custody.  Therefore this view deliberately reports
    ledger facts only: source identity, step counts, terminal export readiness,
    and timestamps.
    """

    rows = recent_calls(limit=limit)
    _print_dict_rows(
        rows,
        (
            "identity",
            "source_identity",
            "created_at",
            "steps",
            "completed",
            "failed",
            "export_ready",
            "exported_at",
        ),
    )


@app.command("steps")
def steps_command(
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="Maximum rows to print."),
    status: list[str] | None = typer.Option(None, "--status", "-s", help="Filter by completed or failed."),
) -> None:
    """Print recent ledgered step rows."""

    statuses = tuple(status or ())
    rows = recent_steps(limit=limit, statuses=statuses)
    _print_step_rows(rows)


@app.command("exports")
def exports_command(
    limit: int = typer.Option(30, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Print recent export custody rows."""

    rows = recent_exports(limit=limit)
    _print_dict_rows(
        rows,
        (
            "identity",
            "source_identity",
            "final_step",
            "result_key",
            "created_at",
            "exported_at",
            "export_message",
        ),
    )


@app.command("results")
def results_command(
    limit: int = typer.Option(30, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Legacy alias: print recent export-backed terminal results."""

    rows = recent_results(limit=limit)
    _print_dict_rows(
        rows,
        (
            "identity",
            "source_identity",
            "final_step",
            "result_key",
            "created_at",
            "exported_at",
            "export_message",
        ),
    )


@app.command("pending")
def pending_command(
    limit: int = typer.Option(50, "--limit", "-n", min=1, help="Maximum rows to print."),
) -> None:
    """Print failed steps plus pending exports.

    Scrivener no longer tracks pending/running workflow state.  This command is
    retained as a convenience inspection surface for work that still needs human
    or export attention.
    """

    rows = pending_work(limit=limit)
    _print_dict_rows(
        rows,
        (
            "identity",
            "source_identity",
            "step_number",
            "final_step",
            "status",
            "result_key",
            "fail_message",
            "created_at",
        ),
    )


@app.command("show")
def show_command(identity: str) -> None:
    """Print one call with its steps and export row as JSON."""

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


@app.command("step")
def step_command(identity: str, step_number: int) -> None:
    """Print one ledgered step as JSON."""

    try:
        data = show_step(identity, step_number)
    except KeyError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _print_step_rows(rows: list[dict[str, Any]]) -> None:
    _print_dict_rows(
        rows,
        (
            "identity",
            "step_number",
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
