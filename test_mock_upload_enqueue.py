"""Mock the feeder upload/enqueue boundary.

Run from the AutoScribe repository root:

    pytest -q test_mock_upload_enqueue.py

The tests do not invoke ``asc`` or Redis. They intercept feeder subprocess
calls and verify the exact NDJSON sent across the pipeline boundary.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path.cwd().resolve()

# Support the current AutoScribe layouts without requiring package installation.
for candidate in (
    ROOT / "feeder" / "src",
    ROOT / "feeder",
    ROOT / "src",
):
    if (candidate / "obs").is_dir():
        sys.path.insert(0, str(candidate))
        break
else:  # pragma: no cover - gives a useful collection-time failure
    raise RuntimeError(
        "Could not find the feeder package. Run pytest from the AutoScribe root "
        "containing feeder/src/obs."
    )

from obs import executables, instruction_upload, plans, process, uploads  # noqa: E402


class CommandCapture:
    """Callable replacement for obs.process.run used by imported modules."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        check: bool = True,
        **_: Any,
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "args": list(args),
                "cwd": Path(cwd).resolve() if cwd is not None else None,
                "input_text": input_text or "",
                "check": check,
            }
        )
        command = " ".join(args)
        return SimpleNamespace(
            stdout=f"mocked: {command}\n",
            stderr="",
            returncode=0,
        )


def decode_ndjson(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def command_tail(call: dict[str, Any]) -> tuple[str, ...]:
    """Ignore the configured path to the asc executable."""

    return tuple(call["args"][-2:])


def assert_upload_contract(record: dict[str, Any], expected_type: str) -> None:
    assert set(record) == {"type", "identity", "content", "extra"}
    assert record["type"] == expected_type
    assert isinstance(record["identity"], str) and record["identity"]
    assert isinstance(record["extra"], dict)


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> CommandCapture:
    captured = CommandCapture()

    # Patch the shared modules first, then reload consumers so any
    # ``from .process import run`` bindings pick up the mock. This avoids
    # assuming every consumer exposes a module-level ``run`` attribute.
    monkeypatch.setattr(process, "run", captured)
    monkeypatch.setattr(executables, "autoscribe_bin", lambda: "asc")
    importlib.reload(instruction_upload)
    importlib.reload(plans)
    importlib.reload(uploads)

    if not hasattr(uploads, "_upload_and_enqueue"):
        pytest.fail(
            "obs.uploads is the pre-refactor version: missing "
            "_upload_and_enqueue(). Install the feeder contract-refactor "
            "replacement files before running this test."
        )

    # Make instruction synchronization deterministic and force both mock
    # instructions to upload during the first run.
    monkeypatch.setattr(instruction_upload, "pipeline_snapshot", lambda _: {})
    monkeypatch.setattr(
        instruction_upload.git,
        "dirty_files",
        lambda _repo: [
            "Instructions/Role.md",
            "Instructions/Specific.md",
        ],
    )
    return captured


def write_instruction(path: Path, slug: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslug: {slug}\n---\n\n{body}\n", encoding="utf-8")


def test_first_run_uploads_control_calls_and_manifest(
    tmp_path: Path,
    capture: CommandCapture,
) -> None:
    """First run uploads instructions, plan, calls, then enqueue manifest."""

    role_path = tmp_path / "Instructions" / "Role.md"
    specific_path = tmp_path / "Instructions" / "Specific.md"
    write_instruction(role_path, "rol.mock-editor.abc123", "Act as an editor.")
    write_instruction(specific_path, "spc.mock-cleanup.def456", "Clean the copy.")

    plan_slug = "plan.mock-cleanup.ghi789"
    plan_record = {
        "record_identity": plan_slug,
        "payload": {
            "label": "Mock cleanup",
            "steps": {
                "1": {
                    "driver_slug": "drv.mock.local",
                    "instruction_slugs": {
                        "role": ["rol.mock-editor.abc123"],
                        "context": [],
                        "specifics": ["spc.mock-cleanup.def456"],
                        "instructions": [],
                    },
                }
            },
        },
    }
    instruction_sets = [
        {
            "slug": "rol.mock-editor.abc123",
            "path": str(role_path),
            "source_path": "Instructions/Role.md",
        },
        {
            "slug": "spc.mock-cleanup.def456",
            "path": str(specific_path),
            "source_path": "Instructions/Specific.md",
        },
    ]

    plan_result = plans.save_plan(
        plan_record,
        cwd=tmp_path,
        instruction_sets=instruction_sets,
    )

    calls = [
        {
            "type": "call",
            "identity": "cnt.mock-one.jkl012",
            "content": "---\nslug: cnt.mock-one.jkl012\n---\n\nFirst mock call.\n",
            "extra": {"filename_hint": "Mock One.md"},
        },
        {
            "type": "call",
            "identity": "prv.compilation.mno345",
            "content": "Compiled external material.\n",
            "extra": {
                "filename_hint": "Compilation.md",
                "source_paths": ["Notes/A.md", "Notes/B.md"],
            },
        },
    ]
    uploads._upload_and_enqueue(tmp_path, calls=calls, plan_slug=plan_slug)

    assert plan_result["record"]["identity"] == plan_slug
    assert len(capture.calls) == 5
    assert command_tail(capture.calls[0]) == ("upload", "instructions")
    assert command_tail(capture.calls[1]) == ("upload", "instructions")
    assert command_tail(capture.calls[2]) == ("upload", "plans")
    assert command_tail(capture.calls[3]) == ("upload", "calls")
    assert capture.calls[4]["args"][-1] == "enqueue"

    instruction_records = [
        decode_ndjson(capture.calls[0]["input_text"])[0],
        decode_ndjson(capture.calls[1]["input_text"])[0],
    ]
    for record in instruction_records:
        assert_upload_contract(record, "instruction")
    assert {record["identity"] for record in instruction_records} == {
        "rol.mock-editor.abc123",
        "spc.mock-cleanup.def456",
    }

    uploaded_plan = decode_ndjson(capture.calls[2]["input_text"])[0]
    assert_upload_contract(uploaded_plan, "plan")
    assert uploaded_plan["identity"] == plan_slug
    assert uploaded_plan["content"] == plan_record["payload"]

    uploaded_calls = decode_ndjson(capture.calls[3]["input_text"])
    assert uploaded_calls == calls
    for record in uploaded_calls:
        assert_upload_contract(record, "call")

    manifest = decode_ndjson(capture.calls[4]["input_text"])
    assert manifest == [
        {"call": "cnt.mock-one.jkl012", "plan": plan_slug},
        {"call": "prv.compilation.mno345", "plan": plan_slug},
    ]


def test_second_run_uploads_only_other_calls_and_manifest(
    tmp_path: Path,
    capture: CommandCapture,
) -> None:
    """Second run reuses control records and uploads only calls plus manifest."""

    plan_slug = "plan.mock-cleanup.ghi789"
    other_calls = [
        {
            "type": "call",
            "identity": "cnt.mock-two.pqr678",
            "content": "---\nslug: cnt.mock-two.pqr678\n---\n\nSecond-run call.\n",
            "extra": {"filename_hint": "Mock Two.md"},
        },
        {
            "type": "call",
            "identity": "prv.external-file.stu901",
            "content": "Imported external text.\n",
            "extra": {"filename_hint": "External File.docx"},
        },
    ]

    uploads._upload_and_enqueue(tmp_path, calls=other_calls, plan_slug=plan_slug)

    assert len(capture.calls) == 2
    assert command_tail(capture.calls[0]) == ("upload", "calls")
    assert capture.calls[1]["args"][-1] == "enqueue"

    uploaded_calls = decode_ndjson(capture.calls[0]["input_text"])
    assert uploaded_calls == other_calls
    for record in uploaded_calls:
        assert_upload_contract(record, "call")

    manifest = decode_ndjson(capture.calls[1]["input_text"])
    assert manifest == [
        {"call": "cnt.mock-two.pqr678", "plan": plan_slug},
        {"call": "prv.external-file.stu901", "plan": plan_slug},
    ]

    # No control uploads should occur in this run.
    assert all(call["args"][-2:] != ["upload", "plans"] for call in capture.calls)
    assert all(call["args"][-2:] != ["upload", "instructions"] for call in capture.calls)
