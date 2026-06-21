import sys
from typing import Any, TextIO

import typer


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Inspect and upload prompt records.",
)


def _report_value(report: Any, name: str) -> int:
    value = getattr(report, name, 0)
    if value is None:
        return 0
    return int(value)


def _upload_prompts_stream(source: TextIO) -> Any:
    """Load the prompt uploader only when this command is invoked.

    Keeping the import local allows `asc --help` and unrelated CLI commands to
    keep working while prompt-side modules are being refactored independently.
    """

    from asc.documents.upload import upload_prompts_stream

    return upload_prompts_stream(source)


@app.command("upload")
def upload_prompts() -> None:
    """Upload prompt records from streamed NDJSON."""

    try:
        report = _upload_prompts_stream(sys.stdin)
    except Exception as exc:
        typer.echo(f"[prompts:upload] error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        "[prompts:upload] uploaded: "
        f"records={_report_value(report, 'record_count')} "
        f"skipped={_report_value(report, 'skipped_count')}",
        err=True,
    )


if __name__ == "__main__":
    app()
