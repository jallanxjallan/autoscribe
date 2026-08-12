"""Worker daemon entrypoint."""

from __future__ import annotations

from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import logging
from threading import Event

from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging
from asc.worker import inbox as worker_inbox
from asc.worker.execute import WorkerExecutor


LOG = logging.getLogger(__name__)
WORKER_THREADS = 4


@dataclass(frozen=True, slots=True)
class WorkerRunReport:
    claimed: bool
    runtime_key: str | None = None
    artifact_key: str | None = None
    failure_key: str | None = None
    action: str | None = None


def process_next(*, timeout: int = 0) -> WorkerRunReport:
    """Claim and execute the next worker runtime."""

    claimed = worker_inbox.daemon_claim(timeout=timeout, empty_limit=None)
    if claimed is None:
        return WorkerRunReport(claimed=False)

    runtime_key = claimed.strip()
    if not runtime_key:
        raise ValueError("worker claimed an empty runtime key")

    LOG.info("worker operation=claimed runtime_key=%s", runtime_key)
    result = WorkerExecutor().execute(runtime_key)

    report = WorkerRunReport(
        claimed=True,
        runtime_key=result.runtime_key,
        artifact_key=result.artifact_key,
        failure_key=result.failure_key,
        action=result.action,
    )
    LOG.info(
        "worker operation=executed runtime_key=%s action=%s artifact_key=%s failure_key=%s",
        report.runtime_key,
        report.action,
        report.artifact_key,
        report.failure_key,
    )
    return report


def _run_thread(
    *,
    thread_number: int,
    timeout: int,
    stop_event: Event,
) -> None:
    """Claim and execute tasks until the worker process is stopped."""

    LOG.info("worker thread start number=%s", thread_number)
    try:
        while not stop_event.is_set():
            report = process_next(timeout=timeout)
            LOG.info(
                "worker thread report number=%s claimed=%s runtime_key=%s action=%s",
                thread_number,
                report.claimed,
                report.runtime_key,
                report.action,
            )
    except Exception:
        LOG.exception("worker thread crash number=%s", thread_number)
        raise
    finally:
        LOG.info("worker thread stop number=%s", thread_number)


def _raise_thread_failure(futures: set[Future[None]]) -> None:
    """Raise the first worker-thread exception, if one occurred."""

    for future in futures:
        if future.done():
            future.result()


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS) -> None:
    """Run four worker threads until process termination."""

    configure_logging()
    LOG.info("worker daemon start threads=%s", WORKER_THREADS)

    stop_event = Event()
    executor = ThreadPoolExecutor(
        max_workers=WORKER_THREADS,
        thread_name_prefix="asc-worker",
    )
    futures = {
        executor.submit(
            _run_thread,
            thread_number=thread_number,
            timeout=timeout,
            stop_event=stop_event,
        )
        for thread_number in range(1, WORKER_THREADS + 1)
    }

    try:
        done, _ = wait(futures, return_when=FIRST_EXCEPTION)
        _raise_thread_failure(done)
        raise RuntimeError("worker thread exited unexpectedly")
    except KeyboardInterrupt:
        LOG.info("worker daemon stop signal=KeyboardInterrupt")
        raise
    except Exception:
        LOG.exception("worker daemon crash")
        raise
    finally:
        stop_event.set()
        executor.shutdown(wait=True, cancel_futures=True)
        LOG.info("worker daemon stop")


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()


__all__ = [
    "WORKER_THREADS",
    "WorkerRunReport",
    "main",
    "process_next",
    "run_forever",
]
