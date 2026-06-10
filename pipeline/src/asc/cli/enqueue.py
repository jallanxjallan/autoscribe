from __future__ import annotations

import sys

import typer

from asc.enqueue.service import enqueue_from_stream

app = typer.Typer(help="Enqueue prompt/plan dispatch records.")


@app.command("-")
def enqueue_stdin() -> None:
    """Read NDJSON dispatch records from stdin and enqueue calls."""

    report = enqueue_from_stream(sys.stdin)
    print(
        "[enqueue] stored: "
        f"records={report.record_count} "
        f"calls={report.call_count}"
    )


@app.callback(invoke_without_command=True)
def enqueue(ctx: typer.Context) -> None:
    """Read NDJSON dispatch records from stdin when no subcommand is given."""

    if ctx.invoked_subcommand is not None:
        return

    report = enqueue_from_stream(sys.stdin)
    print(
        "[enqueue] stored: "
        f"records={report.record_count} "
        f"calls={report.call_count}"
    )
