from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, TextIO

import yaml

from .errors import ObsError
from .process import run


def _pandoc_bin() -> str:
    """Resolve Pandoc without depending on Obsidian's stripped desktop PATH."""
    explicit = os.environ.get("OBSIDIAN_PANDOC_BIN") or os.environ.get("PANDOC_BIN")
    if explicit:
        configured = str(explicit).strip()
        if not configured:
            raise ObsError("configured Pandoc executable is blank")

        # A bare command name such as ``pandoc`` must be resolved through PATH.
        # Only values containing a path separator are treated as filesystem paths.
        if os.path.sep not in configured and (os.path.altsep is None or os.path.altsep not in configured):
            discovered = shutil.which(configured)
            if discovered:
                return discovered
            raise ObsError(f"configured Pandoc command was not found on PATH: {configured}")

        path = Path(configured).expanduser()
        if not path.is_file():
            raise ObsError(f"configured Pandoc executable does not exist: {path}")
        if not os.access(path, os.X_OK):
            raise ObsError(f"configured Pandoc executable is not executable: {path}")
        return str(path)

    candidates = [
        Path.home() / ".local" / "bin" / "pandoc",
        Path("/usr/local/bin/pandoc"),
        Path("/usr/bin/pandoc"),
    ]
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    discovered = shutil.which("pandoc")
    if discovered:
        return discovered

    checked = ", ".join(str(path) for path in candidates)
    raise ObsError(
        "could not locate Pandoc; set OBSIDIAN_PANDOC_BIN or install pandoc "
        f"at one of: {checked}"
    )


def capture(
    *, repo: Path, input_path: str | None = None, input_paths: Iterable[str] | None = None, defaults: Iterable[str], metadata: dict[str, Any]
) -> str:
    defaults = list(defaults)
    paths = list(input_paths or ([] if input_path is None else [input_path]))
    if not paths:
        raise ObsError("pandoc invocation requires at least one input file")
    if not defaults:
        raise ObsError("pandoc invocation requires at least one defaults file")

    with tempfile.TemporaryDirectory(prefix="obs-pandoc-") as temp_dir:
        metadata_file = Path(temp_dir) / "metadata.yaml"
        metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        args = [
            _pandoc_bin(),
            *(f"--defaults={value}" for value in defaults),
            f"--metadata-file={metadata_file}",
            "--output=-",
            *paths,
        ]
        return run(args, cwd=repo).stdout


def emit(
    *,
    repo: Path,
    input_path: str,
    defaults: Iterable[str],
    metadata: dict[str, Any],
    stdout: TextIO,
) -> None:
    """Run the established upload Pandoc shape and emit its NDJSON side output.

    The upload defaults/Lua filter writes the queue record to process stdout;
    Pandoc's document output itself remains discarded at /dev/null, matching
    the former client CLI implementation.
    """
    defaults = list(defaults)
    if not defaults:
        raise ObsError("pandoc invocation requires at least one defaults file")

    with tempfile.TemporaryDirectory(prefix="obs-pandoc-") as temp_dir:
        metadata_file = Path(temp_dir) / "metadata.yaml"
        metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        args = [
            _pandoc_bin(),
            *(f"--defaults={value}" for value in defaults),
            f"--metadata-file={metadata_file}",
            "--output=/dev/null",
            input_path,
        ]
        import subprocess

        result = subprocess.run(
            args,
            cwd=repo,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=None,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ObsError(f"{' '.join(args)} failed with exit status {result.returncode}")
