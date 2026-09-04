from __future__ import annotations

from types import SimpleNamespace

from asc.config.runtime import EXTENSIONS_ROOT
from asc.control.extensions import build_extension_catalog
from asc.extensions import load_runtime_call
from asc.models.process.result import Transform
from asc.models.process.runtime import Runtime


def test_catalog_reads_work_extensions_directly() -> None:
    catalog = build_extension_catalog()

    assert EXTENSIONS_ROOT.as_posix() == "/home/jeremy/Work/Extensions"
    assert catalog["sources"]["extension_root"] == str(EXTENSIONS_ROOT)
    assert "chatgpt" in catalog["registries"]["engines"]
    assert "insert_header" in catalog["registries"]["local_scripts"]


def test_script_runtime_executes_from_work_extensions() -> None:
    runtime = Runtime.model_validate(
        {
            "identity": "direct-extension-test",
            "plan_identity": "test-plan",
            "ordinal": 1,
            "total_steps": 1,
            "engine_kind": "script",
            "engine": "engines.local",
            "script": "insert_header",
        }
    )

    artifact = load_runtime_call(runtime)(SimpleNamespace(content="Test content"))

    assert isinstance(artifact, Transform)
    assert artifact.identity == runtime.identity
    assert artifact.ordinal == runtime.ordinal
    assert artifact.content == (
        "<<<local-transform:insert-header>>>\n\nTest content\n"
    )
