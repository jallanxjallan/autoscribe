from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .errors import ObsError


def _usable_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def autoscribe_bin() -> str:
    """Resolve the AutoScribe CLI without relying on Obsidian's desktop PATH."""
    configured = os.environ.get("AUTOSCRIBE_BIN") or os.environ.get("ASC_BIN")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() or candidate.parent != Path("."):
            candidate = candidate.resolve()
            if not candidate.is_file():
                raise ObsError(f"configured AutoScribe executable does not exist: {candidate}")
            if not os.access(candidate, os.X_OK):
                raise ObsError(f"configured AutoScribe executable is not executable: {candidate}")
            return str(candidate)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise ObsError(f"configured AutoScribe executable is not on PATH: {configured}")

    candidates = [
        # AutoScribe's established Python environment. Desktop-launched Obsidian
        # does not inherit the user's interactive-shell PATH.
        Path.home() / "Python3.13Env" / "bin" / "asc",
        # Useful when feeder itself is launched from the project virtualenv.
        Path(sys.executable).resolve().with_name("asc"),
    ]

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        candidates.insert(0, Path(virtual_env).expanduser() / "bin" / "asc")

    for candidate in candidates:
        if _usable_executable(candidate):
            return str(candidate.resolve())

    resolved = shutil.which("asc")
    if resolved:
        return resolved

    checked = ", ".join(str(path) for path in candidates)
    raise ObsError(
        "could not locate the AutoScribe executable; checked "
        f"{checked}. Set AUTOSCRIBE_BIN to its absolute path."
    )
