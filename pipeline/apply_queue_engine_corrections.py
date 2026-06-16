#!/usr/bin/env python3
"""Apply AutoScribe queue/engine boundary corrections in-place.

Run from the AutoScribe repository root:

    python tools/apply_queue_engine_corrections.py
    python -m compileall src/asc

The script is deliberately text-based and idempotent. It avoids relying on a
previous git patch format and preserves the rest of each file.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path.cwd()
SRC = ROOT / "src" / "asc"


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"updated {path}")


def replace_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        rf"^def {name}\([^\n]*\):\n(?:    .*\n|\n)*?(?=^def |^class |^__all__|\Z)",
        re.M,
    )
    new_text, count = pattern.subn(replacement.rstrip() + "\n\n", text, count=1)
    if count != 1:
        raise RuntimeError(f"could not replace function {name}")
    return new_text


def ensure_import(text: str, line: str) -> str:
    if line in text:
        return text
    future = "from __future__ import annotations\n"
    if text.startswith(future):
        return future + line + "\n" + text[len(future):]
    return line + "\n" + text


def patch_plan_record() -> None:
    path = SRC / "models" / "control" / "plan.py"
    text = read(path)
    text = ensure_import(text, "from typing import Any")

    replacement = '''def step_engine(self, step_number: int) -> str:
    step = self.step(step_number)
    engine = step.get("engine")

    if isinstance(engine, str):
        value = engine.strip()
    elif isinstance(engine, dict):
        raw = engine.get("key") or engine.get("slug") or engine.get("name")
        if not isinstance(raw, str):
            raise ValueError(f"plan step {step_number} engine selector has no string key/slug/name")
        value = raw.strip()
    else:
        raise ValueError(f"plan step {step_number} must provide an engine")

    if not value:
        raise ValueError(f"plan step {step_number} must provide an engine")

    return value.removeprefix("engines.").replace("-", "_")'''

    if "def step_engine(self, step_number: int)" in text:
        text = replace_function(text, "step_engine", replacement)
    else:
        marker = "    def step_args(self, step_number: int)"
        if marker not in text:
            raise RuntimeError("could not find step_engine or step_args insertion point in plan.py")
        text = text.replace(marker, "    " + replacement.replace("\n", "\n    ") + "\n\n" + marker, 1)

    write(path, text)


def patch_worker_engine_loader() -> None:
    path = SRC / "workers" / "engines" / "__init__.py"
    text = read(path)
    text = ensure_import(text, "from typing import Any")

    if "worker engine must be a string module key" not in text:
        text = re.sub(
            r"def load_engine_call\(engine: str, \*, args: ([^\)]*)\):\n",
            r"def load_engine_call(engine: str, *, args: \1):\n"
            r"    if not isinstance(engine, str):\n"
            r"        raise TypeError(f\"worker engine must be a string module key, got {engine!r}\")\n\n",
            text,
            count=1,
        )
    if "worker engine must be a string module key" not in text:
        raise RuntimeError("could not add load_engine_call type guard")

    write(path, text)


def patch_scrivener_runtime() -> None:
    path = SRC / "scrivener" / "runtime.py"
    text = read(path)
    if "scrivener queue received cursor key instead of scrivener job key" in text:
        print(f"already guarded {path}")
        return

    needle = "    job_key = claimed.key\n"
    guard = '''    job_key = claimed.key

    if ":cursor" in job_key:
        raise ValueError(
            f"scrivener queue received cursor key instead of scrivener job key: {job_key}"
        )

    if ":scrivener-job" not in job_key:
        raise ValueError(f"scrivener queue received invalid job key: {job_key}")
'''
    if needle not in text:
        raise RuntimeError("could not find `job_key = claimed.key` in scrivener/runtime.py")
    text = text.replace(needle, guard, 1)
    write(path, text)


def patch_orchestrator_service() -> None:
    path = SRC / "orchestrator" / "service.py"
    if not path.exists():
        print(f"skipping missing {path}")
        return
    text = read(path)

    if "scrivener queue requires scrivener job key" not in text:
        helper = '''

def _assert_scrivener_job_key(job_key: str) -> None:
    if ":cursor" in job_key:
        raise ValueError(f"refusing to enqueue cursor on scrivener queue: {job_key}")
    if ":scrivener-job" not in job_key:
        raise ValueError(f"scrivener queue requires scrivener job key, got {job_key}")
'''
        # Put helpers after imports / protocol definitions if possible; top-level is fine.
        insert_at = text.find("class ")
        if insert_at == -1:
            insert_at = 0
        text = text[:insert_at] + helper + "\n" + text[insert_at:]

    if "_assert_scrivener_job_key(job_key)" not in text:
        text = text.replace(
            "        self.scrivener_queue.insert(job_key)\n",
            "        _assert_scrivener_job_key(job_key)\n        self.scrivener_queue.insert(job_key)\n",
        )

    write(path, text)


def main() -> int:
    if not SRC.exists():
        print("Run this from the repository root; expected src/asc", file=sys.stderr)
        return 2

    patch_plan_record()
    patch_worker_engine_loader()
    patch_scrivener_runtime()
    patch_orchestrator_service()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
