from __future__ import annotations

import logging
from typing import Any, Callable

from asc.scrivener.outcome import save_outcome, scrivener_failure, scrivener_result

log = logging.getLogger(__name__)

Writer = Callable[[Any], Any]


class ScrivenerExecutor:
    """Execute one scrivener job and always persist an outcome artifact."""

    def __init__(self, writer_for_job: Callable[[Any], Writer]):
        self.writer_for_job = writer_for_job

    def execute(self, job: Any) -> str:
        try:
            writer = self.writer_for_job(job)
            writer(job)
            outcome = scrivener_result(job)
        except Exception as exc:
            log.exception("scrivener job failed")
            outcome = scrivener_failure(job, exc)

        return save_outcome(outcome)


__all__ = ["ScrivenerExecutor"]
