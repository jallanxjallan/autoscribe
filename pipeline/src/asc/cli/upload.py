from __future__ import annotations

import sys
from typing import Any, Iterable, TextIO

import typer


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Upload runtime, control, and future asset records from streamed NDJSON.",
)


def _report_value(report: Any, name: str) -> int:
    value = getattr(report, name, 0)
    if value is None:
        return 0
    return int(value)


def _upload_stream(target: str, source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> Any:
    """Load the consolidated uploader only when an upload command is invoked.

    This keeps `asc --help` and unrelated commands resilient while the upload
    package is being refactored independently.
    """

    from asc.upload.uploader import upload_stream

    return upload_stream(source, target=target, error_stream=error_stream)


def _run_upload(target: str) -> None:
    try:
        report = _upload_stream(target, sys.stdin)
    except NotImplementedError as exc:
        typer.echo(f"[upload:{target}] not implemented: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"[upload:{target}] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"[upload:{target}] uploaded: "
        f"records={_report_value(report, 'record_count')} "
        f"skipped={_report_value(report, 'skipped_count')}",
        err=True,
    )


@app.command("instructions")
def upload_instructions() -> None:
    """Upload instruction records from streamed NDJSON."""

    _run_upload("instructions")


@app.command("calls")
def upload_calls() -> None:
    """Upload call records from streamed NDJSON."""

    _run_upload("calls")


@app.command("plans")
def upload_plans() -> None:
    """Upload plan records from streamed NDJSON."""

    _run_upload("plans")


@app.command("assets")
def upload_assets() -> None:
    """Reserved future upload target for asset records."""

    _run_upload("assets")


if __name__ == "__main__":
    app()
