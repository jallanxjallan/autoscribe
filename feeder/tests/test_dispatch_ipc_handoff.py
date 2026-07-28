from __future__ import annotations

from pathlib import Path

import pytest

from obs.errors import ObsError
from obs.ipc import handle


CLIPBOARD_ROWS = [
    ("Regulating The Regulators", "Contents/Regulating The Regulators.md", "cnt.regulating-the-regulators.j9n0c4"),
    ("Advising GOI", "Contents/Advising GOI.md", "cnt.advising-goi.dlpkx0"),
    ("Swiss Verein Network", "Aggregates/Swiss Verein Network.md", "cnt.swiss-verein-network.mock01"),
]


def _write_note(vault: Path, relpath: str, slug: str, body: str) -> None:
    path = vault / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslug: {slug}\n---\n{body}\n", encoding="utf-8")



def _write_plan(vault: Path, slug: str = "plan.test-save-local.97zyee") -> None:
    import json

    path = vault / "_plans" / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "record_type": "plan",
            "record_identity": slug,
            "payload": {
                "label": "Test Save Local",
                "description": "",
                "steps": {
                    "1": {
                        "index": 1,
                        "kind": "llm",
                        "label": "Step 1",
                        "engine": "mock",
                        "model": "mock",
                        "instruction_slugs": {
                            "role": [], "context": [], "specifics": [], "instructions": []
                        },
                    }
                },
            },
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def _dispatch_request(vault: Path, paths: list[str]) -> dict:
    _write_plan(vault)
    return {
        "operation": "dispatch.run",
        "vault": str(vault),
        "paths": paths,
        "plan_slug": "plan.test-save-local.97zyee",
        "dry_run": True,
    }


def test_current_control_handoff_uses_in_place_vault_paths(tmp_path: Path) -> None:
    """Mock the current IPC contract: original paths after in-place flattening."""
    for title, relpath, slug in CLIPBOARD_ROWS:
        _write_note(tmp_path, relpath, slug, f"Flattened body for {title}")

    response = handle(
        _dispatch_request(tmp_path, [relpath for _, relpath, _ in CLIPBOARD_ROWS])
    )

    result = response["result"]
    assert result["dry_run"] is True
    assert result["count"] == 3
    assert [item["path"] for item in result["items"]] == [
        relpath for _, relpath, _ in CLIPBOARD_ROWS
    ]
    assert [item["record_identity"] for item in result["items"]] == [
        slug for _, _, slug in CLIPBOARD_ROWS
    ]
    assert all("Flattened body" in item["record_content"] for item in result["items"])


def test_slugged_aggregate_outside_contents_is_dispatchable(tmp_path: Path) -> None:
    relpath = "Assemblies/Advising GOI Compilation.md"
    slug = "cnt.advising-goi-compilation.mock01"
    _write_note(tmp_path, relpath, slug, "Resolved transclusions saved in place")

    result = handle(_dispatch_request(tmp_path, [relpath]))["result"]

    assert result["count"] == 1
    assert result["items"][0]["path"] == relpath
    assert result["items"][0]["record_identity"] == slug


def test_absolute_path_inside_vault_is_normalized(tmp_path: Path) -> None:
    relpath = "Assemblies/Absolute Input.md"
    slug = "cnt.absolute-input.mock01"
    _write_note(tmp_path, relpath, slug, "Body")

    result = handle(_dispatch_request(tmp_path, [str(tmp_path / relpath)]))["result"]

    assert result["items"][0]["path"] == relpath


def test_dispatch_rejects_file_outside_vault(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-dispatch.md"
    outside.write_text("---\nslug: cnt.outside.mock01\n---\nBody\n", encoding="utf-8")

    with pytest.raises(ObsError, match="outside active vault"):
        handle(_dispatch_request(tmp_path, [str(outside)]))


def test_dispatch_requires_slug(tmp_path: Path) -> None:
    relpath = "Assemblies/Unsugged Aggregate.md"
    path = tmp_path / relpath
    path.parent.mkdir(parents=True)
    path.write_text("---\ntitle: Unsugged Aggregate\n---\nBody\n", encoding="utf-8")

    with pytest.raises(ObsError, match="missing slug"):
        handle(_dispatch_request(tmp_path, [relpath]))
