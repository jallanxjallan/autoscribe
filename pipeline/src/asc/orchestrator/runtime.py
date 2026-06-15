"""Command runtime for the orchestrator daemon."""

from __future__ import annotations

import logging
import os

from .wiring import build_service

log = logging.getLogger(__name__)


def run_once() -> bool:
    return build_service().run_once()


def main() -> None:
    logging.basicConfig(level=os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO"))
    claimed = run_once()
    log.info("orchestrator claimed=%s", claimed)
