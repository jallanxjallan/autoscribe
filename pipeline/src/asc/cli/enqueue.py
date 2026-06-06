from __future__ import annotations

import sys

import typer

from asc.enqueue.service import enqueue_from_stream

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
    help="Freeze streamed typed prompt records into runtime call keys.",
)


@app.callback()
def enqueue() -> None:
    try:
        report = enqueue_from_stream(sys.stdin)
    except Exception as exc:
        typer.echo(f"[enqueue] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        "[enqueue] stored: "
        f"records={report.record_count} "
        f"calls={report.call_count} "
        f"steps={report.step_count}"
    )
