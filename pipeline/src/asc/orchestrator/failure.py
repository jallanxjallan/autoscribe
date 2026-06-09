from __future__ import annotations

import logging

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.step import insert_step_record_with_connection
from asc.models.runtime.result import StepResultRecord

log = logging.getLogger(__name__)


def handle_failure(*, conn: LedgerConnection, result: StepResultRecord) -> None:
    """Persist a failed step and stop pipeline progression.

    This is deliberately small for now. Later this module should own failure
    classification, failure-list appends, human-review flags, and permanent
    versus retryable failure decisions.
    """

    insert_step_record_with_connection(
        conn=conn,
        result=result,
        commit=False,
    )
    log.warning("Recorded failed step result; pipeline progression stopped")
