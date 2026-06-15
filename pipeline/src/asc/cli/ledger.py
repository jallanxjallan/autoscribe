from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

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
from asc.scrivener.lifecycle import (
    active_ledger_path,
    ensure_active_ledger,
    reset_ledger,
    rotate_ledger,
)


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Manage and inspect the SQLite ledger.",
)


@app.command("path")
def path_command() -> None:
    """Print the configured active ledger path."""

    typer.echo(str(active_ledger_path()))


@app.command("init")
def init_command() -> None:
    """Create or update the active ledger schema without deleting data."""

    path = ensure_active_ledger()
    typer.echo(f"ledger init: ensured schema: {path}")


@app.command("reset")
def reset_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Actually drop and recreate ledger tables. Without this flag, reset is a dry run.",
        ),
    ] = False,
) -> None:
    """Drop and recreate the active ledger schema for development cycles."""

    report = reset_ledger(apply=apply)
    if not report.applied:
        typer.echo("ledger reset: dry run only; no tables were dropped", err=True)
        typer.echo(f"ledger reset: would reset: {report.ledger_path}", err=True)
        typer.echo("ledger reset: rerun with --apply to execute", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"ledger reset: reset active ledger: {report.ledger_path}")


@app.command("rotate")
def rotate_command(
    archive_dir: Annotated[
        Path | None,
        typer.Option(
            "--archive-dir",
            "-a",
            help="Directory where archived ledgers should be stored.",
        ),
    ] = None,
) -> None:
    """Archive the ledger and move unfinished row families into a fresh ledger."""

    report = rotate_ledger(archive_dir=archive_dir)
    if report.archive_path is None:
        typer.echo(f"ledger rotate: no existing ledger found; initialized: {report.active_path}")
        return

    typer.echo(f"ledger rotate: archived ledger: {report.archive_path}")
    typer.echo(f"ledger rotate: active ledger:   {report.active_path}")
    typer.echo(
        "ledger rotate: carried forward: "
        f"calls={report.carried_calls} "
        f"steps={report.carried_steps} "
        f"results={report.carried_results} "
        f"exports={report.carried_exports}"
    )
    typer.echo(
        "ledger rotate: removed from archive: "
        f"calls={report.old_deleted_calls} "
        f"steps={report.old_deleted_steps} "
        f"results={report.old_deleted_results} "
        f"exports={report.old_deleted_exports}"
    )


@app.command("tables")
def tables_command() -> None:
    """Print row counts for ledger tables."""

    rows = [(item.table, item.rows) for item in table_counts()]
    _print_table(("table", "rows"), rows)


@app.command("calls")
def calls_command(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 20,
) -> None:
    """Print recent calls."""

    rows = recent_calls(limit=limit)
    _print_dict_table(
        rows,
        ("call", "plan", "source_identifier", "steps", "pending", "running", "completed", "failed"),
    )


@app.command("steps")
def steps_command(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 50,
) -> None:
    """Print recent steps."""

    _print_step_rows(recent_steps(limit=limit))


@app.command("pending")
def pending_command(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 50,
) -> None:
    """Print pending, running, and failed steps."""

    _print_step_rows(pending_work(limit=limit))


@app.command("results")
def results_command(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 30,
) -> None:
    """Print recent result pointers."""

    _print_dict_table(
        recent_results(limit=limit),
        ("result", "call", "terminal_step_id", "exported", "created_at"),
    )


@app.command("exports")
def exports_command(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 30,
) -> None:
    """Print recent export records."""

    _print_dict_table(
        recent_exports(limit=limit),
        ("result", "call", "export_message", "created_at"),
    )


@app.command("show-call")
def show_call_command(call: str) -> None:
    """Print a single call family."""

    data = show_call(call)
    call_row = data["call"]
    raw = data.get("raw") or {}

    typer.echo("Call")
    typer.echo(f"  call:    {call_row.get('call', '')}")
    typer.echo(f"  plan:    {call_row.get('plan', '')}")
    typer.echo(f"  source:  {raw.get('identifier') or raw.get('slug') or '' if isinstance(raw, dict) else ''}")
    typer.echo(f"  created: {call_row.get('created_at', '')}")
    typer.echo("")

    typer.echo("Steps")
    _print_dict_table(
        data["steps"],
        ("step_number", "status", "handler", "engine", "input_key", "output_key", "fail_message"),
        empty_message="  none",
    )
    typer.echo("")

    result = data.get("result")
    typer.echo("Result")
    if result:
        typer.echo(f"  result:           {result.get('result', '')}")
        typer.echo(f"  terminal_step_id: {result.get('terminal_step_id', '')}")
    else:
        typer.echo("  none")
    typer.echo("")

    export = data.get("export")
    typer.echo("Export")
    if export:
        typer.echo(f"  result:  {export.get('result', '')}")
        typer.echo(f"  message: {export.get('export_message', '')}")
    else:
        typer.echo("  none")


@app.command("show-step")
def show_step_command(call: str, step_number: int) -> None:
    """Print a single step with prompt/response excerpts."""

    step = show_step(call, step_number)
    typer.echo(f"call:      {step.get('call', '')}")
    typer.echo(f"step:      {step.get('step_number', '')}")
    typer.echo(f"status:    {step.get('status', '')}")
    typer.echo(f"handler:   {step.get('handler', '')}")
    typer.echo(f"engine:    {step.get('engine', '')}")
    typer.echo(f"input_key: {step.get('input_key', '')}")
    typer.echo(f"output_key:{step.get('output_key', '')}")
    typer.echo(
        "tokens:    "
        f"prompt={step.get('prompt_tokens') or ''} "
        f"completion={step.get('completion_tokens') or ''} "
        f"total={step.get('total_tokens') or ''}"
    )
    if step.get("fail_message"):
        typer.echo(f"failure:   {step['fail_message']}")
    typer.echo("")
    typer.echo("prompt:")
    typer.echo(_excerpt(step.get("prompt")))
    typer.echo("")
    typer.echo("response:")
    typer.echo(_excerpt(step.get("response")))


def _print_step_rows(rows: list[dict[str, Any]]) -> None:
    _print_dict_table(
        rows,
        ("call", "step_number", "status", "handler", "engine", "fail_message"),
    )


def _print_dict_table(
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    *,
    empty_message: str = "no rows",
) -> None:
    rendered = [tuple(_format_value(row.get(col)) for col in columns) for row in rows]
    _print_table(columns, rendered, empty_message=empty_message)


def _print_table(
    headers: tuple[str, ...],
    rows: list[tuple[Any, ...]],
    *,
    empty_message: str = "no rows",
) -> None:
    if not rows:
        typer.echo(empty_message)
        return

    rendered_rows = [tuple(_format_value(value) for value in row) for row in rows]
    widths = [len(header) for header in headers]
    for row in rendered_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    typer.echo("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    typer.echo("  ".join("─" * width for width in widths))
    for row in rendered_rows:
        typer.echo("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("\n", " ")


def _excerpt(value: Any, *, limit: int = 700) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


if __name__ == "__main__":
    app()
