from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

OBS_BIN = "/home/jeremy/Python3.13Env/bin/obs"


def _request() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("dispatch request must be a JSON object")
    return value


def main() -> int:
    try:
        request = _request()
        root = Path(str(request.get("vault_root") or "")).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"invalid vault root: {root}")

        items = request.get("items")
        if not isinstance(items, list):
            raise ValueError("dispatch request requires items list")
        paths = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("dispatch item must be an object")
            path = str(item.get("path") or "").strip()
            if not path:
                raise ValueError("dispatch item is missing path")
            paths.append(path)

        plan_slug = str(request.get("plan_slug") or "").strip()
        if not plan_slug:
            raise ValueError("dispatch request requires plan_slug")

        ipc_request = {
            "operation": "dispatch.run",
            "paths": paths,
            "plan_slug": plan_slug,
        }
        result = subprocess.run(
            [OBS_BIN, "--vault", str(root), "ipc"],
            cwd=root,
            input=json.dumps(ipc_request, ensure_ascii=False),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            response = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            detail = (result.stderr or result.stdout or f"exit status {result.returncode}").strip()
            raise RuntimeError(f"obs ipc returned invalid JSON: {detail}") from exc

        if result.returncode != 0 or response.get("ok") is False:
            detail = response.get("error") or result.stderr or result.stdout or f"exit status {result.returncode}"
            raise RuntimeError(str(detail).strip())

        dispatch = response.get("result") or {}
        dispatched = int(dispatch.get("count", 0))
        failed = int(dispatch.get("failed_count", len(dispatch.get("failures") or [])))
        message = f"Dispatched {dispatched} record(s) with {plan_slug}."
        if failed:
            message += f" {failed} file(s) failed."
        print(json.dumps({
            "ok": True,
            "message": message,
            "result": dispatch,
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
