"""User-facing run commands."""

from __future__ import annotations

import typer
from typing_extensions import Annotated

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Run queued atomic steps.",
)


def _emit_result(*, mode: str, processed: int) -> None:
    typer.echo(f"mode={mode}")
    typer.echo(f"processed_steps={processed}")


@app.command("once")
def run_once() -> None:
    """Claim one queued step, immediately requeue it, print a custody summary, then stop."""

    from asc.execute.workers.once import OnceWorker

    processed = int(OnceWorker().run())
    _emit_result(mode="once", processed=processed)


@app.command("drain")
def run_drain(
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Accepted for CLI compatibility; currently only affects the drain notice.",
        ),
    ] = False,
) -> None:
    """Inspect one queued step and immediately requeue it."""

    from asc.execute.workers.drain import DrainWorker

    processed = int(DrainWorker(quiet=quiet).run())
    _emit_result(mode="drain", processed=processed)


if __name__ == "__main__":
    app()
