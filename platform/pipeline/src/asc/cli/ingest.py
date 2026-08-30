from pathlib import Path

import typer

from asc.ingest.common import IngestInputError
from asc.ingest.git_revision import ingest_git_revision
from asc.models.process.result import record_failure

app = typer.Typer(
    invoke_without_command=True,
    add_completion=False,
    help="Materialize plans and instructions from a Git revision into Redis.",
)


@app.callback(invoke_without_command=True)
def ingest(
    repository: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    revision: str = typer.Argument(...),
    base: str | None = typer.Option(None, "--base", help="Diff from this previously ingested revision."),
    full: bool = typer.Option(False, "--full", help="Rebuild plan/instruction Redis materialization from the snapshot."),
) -> None:
    try:
        report = ingest_git_revision(repository, revision, base=base, full=full)
    except IngestInputError as exc:
        failure_key = record_failure(stage="ingest.git", exc=exc, target=str(repository))
        typer.echo(f"asc ingest: {exc} failure_key={failure_key}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        failure_key = record_failure(stage="ingest.git", exc=exc, target=str(repository))
        typer.echo(f"asc ingest: {exc} failure_key={failure_key}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        "[ingest] materialized: "
        f"records={report.record_count} "
        f"instructions={report.by_type.get('instruction', 0)} "
        f"plans={report.by_type.get('plan', 0)}"
    )


if __name__ == "__main__":
    app()
