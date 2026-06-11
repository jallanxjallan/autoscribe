"""User-facing run commands.

The run CLI is intentionally orchestrator-first.  Enqueue materializes calls and submits call_state keys. Workers receive the
mutable call_state key, load the immutable uploaded plan step indicated by that
state, write the next content artifact, and return the call_state only after
success or worker-scoped retries are exhausted. The orchestrator owns artifact
verification, pipeline progression, ledger writes, and final result detection.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

import typer
from typing_extensions import Annotated

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Run AutoScribe orchestration and worker queues.",
)


def _emit_result(*, mode: str, processed: int) -> None:
    typer.echo(f"mode={mode}")
    typer.echo(f"processed={processed}")


def _load_attr(module_name: str, attr_name: str) -> Any:
    """Import an attribute and raise a clean Typer error if it is unavailable."""

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise typer.BadParameter(
            f"Required module is not available: {module_name}"
        ) from exc

    try:
        return getattr(module, attr_name)
    except AttributeError as exc:
        raise typer.BadParameter(
            f"Required attribute is not available: {module_name}.{attr_name}"
        ) from exc


def _run_service(
    *,
    module_name: str,
    class_name: str,
    method_name: str = "run",
    **kwargs: Any,
) -> int:
    """Instantiate a service class and run it, returning an integer count."""

    service_class = _load_attr(module_name, class_name)
    service = service_class(**kwargs)
    method: Callable[[], Any] = getattr(service, method_name)
    return int(method())


@app.command("start")
def run_start() -> None:
    """Claim one submitted call_state, ledger it, and enqueue it for worker custody."""

    processed = _run_service(
        module_name="asc.orchestrator.start",
        class_name="StartOrchestrator",
    )
    _emit_result(mode="start", processed=processed)


@app.command("response")
def run_response() -> None:
    """Claim one returned call_state and advance, fail, or finalize it."""

    processed = _run_service(
        module_name="asc.orchestrator.daemon",
        class_name="OrchestratorDaemon",
    )
    _emit_result(mode="response", processed=processed)


@app.command("once")
def run_once(
    include_worker: Annotated[
        bool,
        typer.Option(
            "--worker/--no-worker",
            help=(
                "Run one worker step between orchestrator passes. "
                "Default keeps the command useful as a local smoke test."
            ),
        ),
    ] = True,
) -> None:
    """Run one local custody cycle: start call_state, optionally execute worker custody, process returned state."""

    processed = 0

    # Start any newly-submitted call before letting a worker claim work.
    try:
        processed += _run_service(
            module_name="asc.orchestrator.start",
            class_name="StartOrchestrator",
        )
    except typer.BadParameter:
        # Older trees may not yet have the split start module.  Let the
        # response daemon command surface the import error when called directly.
        pass

    if include_worker:
        from asc.workers.once import OnceWorker

        processed += int(OnceWorker().run())

    processed += _run_service(
        module_name="asc.orchestrator.daemon",
        class_name="OrchestratorDaemon",
    )
    _emit_result(mode="once", processed=processed)


@app.command("drain")
def run_drain(
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress per-cycle notices where supported.",
        ),
    ] = False,
    max_cycles: Annotated[
        int,
        typer.Option(
            "--max-cycles",
            min=1,
            help="Maximum orchestration/worker cycles to run.",
        ),
    ] = 100,
) -> None:
    """Drain submitted call_state keys, worker custody, and returned states until idle."""

    from asc.workers.drain import DrainWorker

    processed = 0

    for _ in range(max_cycles):
        cycle_count = 0

        try:
            cycle_count += _run_service(
                module_name="asc.orchestrator.start",
                class_name="StartOrchestrator",
            )
        except typer.BadParameter:
            pass

        cycle_count += int(DrainWorker(quiet=quiet).run())
        cycle_count += _run_service(
            module_name="asc.orchestrator.daemon",
            class_name="OrchestratorDaemon",
        )

        processed += cycle_count
        if cycle_count == 0:
            break

    _emit_result(mode="drain", processed=processed)


@app.command("state")
def run_state() -> None:
    """Print a lightweight queue/state summary for the orchestrated pipeline."""

    # Keep this deliberately loose while the state package is still settling:
    # if a queue module exists and exposes a count/length function, report it.
    queue_modules = {
        "calls": "asc.state.call_queue",
        "workers": "asc.state.worker_queue",
        "steps_compat": "asc.state.step_queue",
        "responses": "asc.state.response_queue",
        "failures": "asc.state.failure_queue",
    }

    for label, module_name in queue_modules.items():
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            typer.echo(f"{label}=unavailable")
            continue

        value = "unknown"
        for attr_name in ("count", "length", "llen", "size"):
            attr = getattr(module, attr_name, None)
            if callable(attr):
                try:
                    value = str(attr())
                    break
                except TypeError:
                    continue

        typer.echo(f"{label}={value}")


if __name__ == "__main__":
    app()
