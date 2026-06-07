from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer

from asc.ledger.connect import configured_ledger_path
from asc.ledger.load import init_database


DEFAULT_ARCHIVE_DIRNAME = "archive"


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Manage AutoScribe storage, ledger rotation, and result persistence.",
)


def timestamp_label() -> str:
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    return now.strftime("%Y%m%dT%H%M%S%z")


def archive_path_for(ledger_path: Path, archive_dir: Path) -> Path:
    suffix = ledger_path.suffix or ".sql"
    stem = ledger_path.stem
    return archive_dir / f"{stem}.{timestamp_label()}{suffix}"


def rotate_ledger(
    *,
    archive_dir: Path | None = None,
) -> tuple[Path | None, Path]:
    ledger_path = configured_ledger_path().expanduser().resolve()

    if archive_dir is None:
        archive_dir = ledger_path.parent / DEFAULT_ARCHIVE_DIRNAME
    else:
        archive_dir = archive_dir.expanduser().resolve()

    archived_to: Path | None = None

    if ledger_path.exists():
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_to = archive_path_for(ledger_path, archive_dir)

        if archived_to.exists():
            raise FileExistsError(f"archive target already exists: {archived_to}")

        ledger_path.rename(archived_to)

    init_database(force=False)
    initialized = configured_ledger_path().expanduser().resolve()

    return archived_to, initialized


@app.command("rotate-db")
def rotate_db_command(
    archive_dir: Annotated[
        Path | None,
        typer.Option(
            "--archive-dir",
            "-a",
            help="Directory where archived ledgers should be stored.",
        ),
    ] = None,
) -> None:
    """
    Rename the configured ledger as a timestamped archive and initialize a new ledger.
    """

    archived_to, initialized = rotate_ledger(archive_dir=archive_dir)

    if archived_to is None:
        typer.echo("storage rotate-db: no existing ledger found")
    else:
        typer.echo(f"storage rotate-db: archived ledger: {archived_to}")

    typer.echo(f"storage rotate-db: initialized ledger: {initialized}")


@app.command("start")
def start_command() -> None:
    """Start the storage persistence process when lifecycle wiring is available."""

    typer.echo("storage start not wired yet")


@app.command("stop")
def stop_command() -> None:
    """Stop the storage persistence process when lifecycle wiring is available."""

    typer.echo("storage stop not wired yet")


@app.command("status")
def status_command() -> None:
    """Show storage persistence status when lifecycle wiring is available."""

    typer.echo("storage status not wired yet")


if __name__ == "__main__":
    app()
