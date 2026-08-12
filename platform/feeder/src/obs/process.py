from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

from .errors import ObsError


def run(
    args: Iterable[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [str(part) for part in args]
    result = subprocess.run(
        command,
        cwd=cwd,
        env=os.environ.copy(),
        input=input_text,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit status {result.returncode}").strip()
        raise ObsError(f"{' '.join(command)} failed: {detail}")
    return result
