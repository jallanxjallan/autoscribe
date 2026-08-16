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


def _ipc(root: Path, payload: dict[str, Any]) -> Any:
    result = subprocess.run(
        [OBS_BIN, "--vault", str(root), "ipc"],
        cwd=root,
        input=json.dumps(payload, ensure_ascii=False),
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
    return response.get("result")


def main() -> int:
    try:
        request = _request()
        root = Path(str(request.get("vault_root") or "")).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"invalid vault root: {root}")

        operation = str(request.get("operation") or "").strip()
        if operation == "list_commits":
            result = _ipc(root, {"operation": "git.user_commits", "limit": int(request.get("limit") or 100)})
            message = f"Loaded {len(result or [])} dispatchable commit(s)."
        elif operation == "commit_state":
            commit = str(request.get("commit") or "").strip()
            if not commit:
                raise ValueError("commit_state requires commit")
            result = _ipc(root, {"operation": "git.commit_state", "commit": commit})
            message = f"Loaded {len((result or {}).get('files') or [])} commit member(s)."
        elif operation == "dispatch":
            commit = str(request.get("commit") or "").strip()
            plan_slug = str(request.get("plan_slug") or "").strip()
            if not commit:
                raise ValueError("dispatch requires commit")
            if not plan_slug:
                raise ValueError("dispatch requires plan_slug")
            result = _ipc(root, {
                "operation": "dispatch.commit",
                "commit": commit,
                "plan_slug": plan_slug,
            })
            message = f"Dispatched {int((result or {}).get('count') or 0)} record(s) from {commit[:8]} with {plan_slug}."
        else:
            raise ValueError(f"unknown helper operation: {operation or '<empty>'}")

        print(json.dumps({"ok": True, "message": message, "result": result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
