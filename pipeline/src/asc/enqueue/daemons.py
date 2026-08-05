"""Ensure the AutoScribe runtime daemons are available before enqueueing work."""

from __future__ import annotations

import shutil
import subprocess


class PipelineDaemonStartError(RuntimeError):
    """Raised when the pipeline daemon launcher cannot be run successfully."""


def ensure_pipeline_daemons_running() -> None:
    """Start any missing pipeline daemons via the production lifecycle command.

    ``asc run start`` is intentionally idempotent: it starts missing daemons and
    leaves already-running daemons alone. Calling it for every enqueue operation
    therefore also repairs a partially stopped pipeline before work is exposed.
    """

    asc_command = shutil.which("asc")
    if asc_command is None:
        raise PipelineDaemonStartError(
            "cannot start pipeline daemons because the 'asc' command is not on PATH"
        )

    completed = subprocess.run(
        [asc_command, "run", "start"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return

    detail = completed.stderr.strip() or completed.stdout.strip()
    message = f"'asc run start' exited with status {completed.returncode}"
    if detail:
        message = f"{message}: {detail}"
    raise PipelineDaemonStartError(message)


__all__ = ["PipelineDaemonStartError", "ensure_pipeline_daemons_running"]
