from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

import yaml

from .errors import ObsError
from .process import run


def capture(
    *, repo: Path, input_path: str, defaults: Iterable[str], metadata: dict[str, Any]
) -> str:
    pandoc = os.environ.get("OBSIDIAN_PANDOC_BIN")
    if not pandoc:
        raise ObsError("OBSIDIAN_PANDOC_BIN is not set")
    defaults = list(defaults)
    if not defaults:
        raise ObsError("pandoc invocation requires at least one defaults file")
    with tempfile.TemporaryDirectory(prefix="obs-pandoc-") as temp_dir:
        metadata_file = Path(temp_dir) / "metadata.yaml"
        metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        args = [pandoc, *(f"--defaults={value}" for value in defaults),
                f"--metadata-file={metadata_file}", "--output=-", input_path]
        return run(args, cwd=repo).stdout
