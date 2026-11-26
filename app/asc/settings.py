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


def ledger_path(configuration=Path('/etc/autoscribe/services.toml')) -> Path:
    """Resolve the single runtime ledger setting; never create or fall back."""
    import sqlite3
    import tomllib
    value = tomllib.loads(configuration.read_text())['paths']['ledger_db']
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('paths.ledger_db must be an absolute database path')
    path = Path(value).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.R_OK | os.W_OK) or not os.access(path.parent, os.W_OK | os.X_OK):
        raise ValueError('Configured ledger is not accessible: ' + str(path))
    connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
    try:connection.execute("PRAGMA schema_version").fetchone()
    finally:connection.close()
    return path
