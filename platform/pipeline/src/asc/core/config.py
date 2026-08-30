from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
SQL_LEDGER_PATH = Path(
    os.environ.get("SQL_LEDGER_PATH", "~/.local/share/autoscribe/db/ledger.sql")
).expanduser()

# Runtime components live under the platform tree. This root must be the
# parent of engines/ and scripts/. Explicit environment values remain
# authoritative so packaged deployments can relocate the platform.
_WORK_ROOT = Path(os.environ.get("WORK_ROOT", "~/Work")).expanduser()
_AUTOSCRIBE_ROOT = Path(
    os.environ.get("AUTOSCRIBE_ROOT", str(_WORK_ROOT / "AutoScribe"))
).expanduser()
_AUTOSCRIBE_PLATFORM = Path(
    os.environ.get("AUTOSCRIBE_PLATFORM", str(_AUTOSCRIBE_ROOT / "platform"))
).expanduser()
AUTOSCRIBE_EXTENSIONS_ROOT = Path(
    os.environ.get(
        "AUTOSCRIBE_EXTENSIONS_ROOT",
        str(_AUTOSCRIBE_PLATFORM / "extensions"),
    )
).expanduser().resolve()
# AutoScribe Control migration override
AUTOSCRIBE_EXTENSIONS_ROOT = Path('/home/jeremy/Work/Control').expanduser().resolve()
AUTOSCRIBE_ENGINE_PACKAGES = ("engines",)
AUTOSCRIBE_SCRIPT_PACKAGES = ("scripts",)

_SECRET_FILES = (
    Path(".env"),
    Path("~/.secrets.env").expanduser(),
)
_SECRETS_LOADED = False


class ConfigError(RuntimeError):
    pass


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            raise ConfigError(f"Invalid env line in {path}: {line.rstrip()}")

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        if not key:
            raise ConfigError(f"Empty env key in {path}: {line.rstrip()}")
        os.environ.setdefault(key, value)


def load_secrets() -> None:
    global _SECRETS_LOADED
    if _SECRETS_LOADED:
        return
    for path in _SECRET_FILES:
        _load_env_file(path.expanduser())
    _SECRETS_LOADED = True


def secret(*names: str, default: str | None = None) -> str | None:
    load_secrets()
    for name in names:
        value = os.environ.get(name)
        if value not in {None, ""}:
            return value
    return default


def require_secret(*names: str) -> str:
    value = secret(*names)
    if value not in {None, ""}:
        return value
    joined = " or ".join(names)
    raise ConfigError(f"Missing required secret: set {joined} in the environment, .env, or ~/.secrets.env")


def ensure_runtime_paths() -> None:
    """Validate configured runtime paths without changing Python import state."""

    if not AUTOSCRIBE_EXTENSIONS_ROOT.is_dir():
        raise FileNotFoundError(
            f"AutoScribe extensions root not found: {AUTOSCRIBE_EXTENSIONS_ROOT}"
        )


@dataclass(frozen=True)
class Config:
    redis_url: str = REDIS_URL
    sql_ledger_path: Path = SQL_LEDGER_PATH
    extensions_root: Path = AUTOSCRIBE_EXTENSIONS_ROOT

    @property
    def open_ai_key(self) -> str:
        return require_secret("OPENAI_API_KEY", "OPEN_AI_KEY")

    @property
    def anthropic_key(self) -> str:
        return require_secret("ANTHROPIC_API_KEY")


config = Config()


__all__ = [
    "AUTOSCRIBE_ENGINE_PACKAGES",
    "AUTOSCRIBE_EXTENSIONS_ROOT",
    "AUTOSCRIBE_SCRIPT_PACKAGES",
    "Config",
    "ConfigError",
    "REDIS_URL",
    "SQL_LEDGER_PATH",
    "config",
    "ensure_runtime_paths",
    "load_secrets",
    "require_secret",
    "secret",
]
