import sys
from typing import Any, Iterable, TextIO

import typer


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Ingest runtime, control, and content records from streamed NDJSON.",
)


def _report_value(report: Any, name: str) -> int:
    value = getattr(report, name, 0)
    if value is None:
        return 0
    return int(value)


def _ingest_stream(target: str, source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> Any:
    """Load the ingest package only when an ingest command is invoked."""

    from asc.ingest.stream import ingest_stream

    return ingest_stream(source, target=target, error_stream=error_stream)


def _run_ingest(target: str) -> None:
    try:
        report = _ingest_stream(target, sys.stdin)
    except NotImplementedError as exc:
        typer.echo(f"[ingest:{target}] not implemented: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"[ingest:{target}] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"[ingest:{target}] ingested: "
        f"records={_report_value(report, 'record_count')} "
        f"skipped={_report_value(report, 'skipped_count')}",
        err=True,
    )


@app.command("instructions")
def ingest_instructions() -> None:
    """Ingest instruction records from streamed NDJSON."""

    _run_ingest("instructions")


@app.command("content")
def ingest_content() -> None:
    """Ingest content records from streamed NDJSON."""

    _run_ingest("content")


@app.command("calls")
def ingest_calls() -> None:
    """Compatibility alias for content records."""

    _run_ingest("content")


@app.command("plans")
def ingest_plans() -> None:
    """Ingest plan records from streamed NDJSON."""

    _run_ingest("plans")


@app.command("records")
def ingest_any_records() -> None:
    """Ingest mixed NDJSON records and route each record by record_type."""

    _run_ingest("all")


if __name__ == "__main__":
    app()
