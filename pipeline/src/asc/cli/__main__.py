from __future__ import annotations

import typer

from asc.cli.control import app as control_app
from asc.cli.enqueue import app as enqueue_app
from asc.cli.export import app as export_app
from asc.cli.registry import app as registry_app
from asc.cli.run import app as run_app
from asc.cli.storage import app as storage_app
from asc.cli.upload import app as upload_app


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_short=False,
    pretty_exceptions_show_locals=True,
    help="AutoScribe command line interface.",
)

app.add_typer(
    control_app,
    name="control",
    help="Manage reusable control assets.",
)

app.add_typer(
    upload_app,
    name="upload",
    help="Upload instructions, calls, plans, and future assets.",
)

app.add_typer(
    enqueue_app,
    name="enqueue",
    help="Freeze uploaded call records and queue them.",
)

app.add_typer(
    run_app,
    name="run",
    help="Run queued calls.",
)

app.add_typer(
    storage_app,
    name="storage",
    help="Manage storage, ledger rotation, and result persistence.",
)

app.add_typer(
    export_app,
    name="export",
    help="Export completed results.",
)

app.add_typer(
    registry_app,
    name="registry",
    help="Inspect and register runtime components.",
)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
