"""One runtime retention policy; the accepted call snapshots its selected value."""
import os
from pathlib import Path
DEFAULT_RUNTIME_RETENTION_SECONDS = 72 * 60 * 60

def retention_seconds() -> int:
    value=int(os.environ.get('AUTOSCRIBE_RUNTIME_RETENTION_SECONDS',DEFAULT_RUNTIME_RETENTION_SECONDS))
    if value<1:raise ValueError('Runtime retention must be a positive number of seconds')
    return value


def release_identity() -> str:
    return Path(os.environ["AUTOSCRIBE_RELEASE_ROOT"]).resolve().name
