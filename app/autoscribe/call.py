from __future__ import annotations
from datetime import datetime, timezone


def build_call_record(*, repo: str, repo_name: str, commit: str, ref: str | None, plan: dict, sources: list[dict]) -> dict:
    return {
        "schema": "autoscribe.call.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"repo": repo, "repo_name": repo_name, "commit": commit, "ref": ref},
        "sources": sources,
        "plan": plan,
    }
