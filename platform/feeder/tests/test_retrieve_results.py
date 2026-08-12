from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from obs.retrieval import retrieve_results


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()


def _flight(repo: Path, branch: str, records: list[dict[str, str]]) -> None:
    _git(repo, "checkout", "-b", branch)
    path = repo / ".autoscribe" / "dispatch.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"branch": branch, "run_identity": branch.rsplit("/", 1)[-1], "records": records}), encoding="utf-8")
    _git(repo, "add", str(path.relative_to(repo)))
    _git(repo, "commit", "-m", branch)
    _git(repo, "checkout", "master")


def test_retrieve_results_extracts_each_waiting_flight(tmp_path: Path, monkeypatch) -> None:
    _git(tmp_path, "init", "-b", "master")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README").write_text("root\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "root")

    _flight(tmp_path, "autoscribe/run/flight-one", [
        {"identity": "cnt.one", "source_path": "Contents/One.md"},
        {"identity": "cnt.two", "source_path": "Contents/Two.md"},
    ])
    _flight(tmp_path, "autoscribe/run/flight-two", [
        {"identity": "cnt.three", "source_path": "Contents/Three.md"},
    ])

    calls: list[list[str]] = []

    def fake_run(command, *, cwd, **kwargs):
        calls.append(command)
        identities = command[3:]
        stdout = "".join(
            json.dumps({"record_identity": identity, "call_identity": f"call-{identity}", "content": f"Result {identity}"}) + "\n"
            for identity in identities
        )
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    monkeypatch.setattr("obs.retrieval.autoscribe_bin", lambda: "asc")
    monkeypatch.setattr("obs.retrieval.run", fake_run)

    rows = retrieve_results(tmp_path)

    assert calls == [
        ["asc", "export", "extract-selected", "cnt.one", "cnt.two"],
        ["asc", "export", "extract-selected", "cnt.three"],
    ]
    assert [row["record_identity"] for row in rows] == ["cnt.one", "cnt.two", "cnt.three"]
    assert rows[0]["transport_branch"] == "autoscribe/run/flight-one"
    assert rows[2]["source_path"] == "Contents/Three.md"


def test_retrieve_results_dry_run_does_not_call_asc(tmp_path: Path, monkeypatch) -> None:
    _git(tmp_path, "init", "-b", "master")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README").write_text("root\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "root")
    _flight(tmp_path, "autoscribe/run/flight-one", [{"identity": "cnt.one", "source_path": "One.md"}])

    monkeypatch.setattr("obs.retrieval.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("asc called")))

    assert retrieve_results(tmp_path, dry_run=True) == [{
        "record_identity": "cnt.one",
        "source_path": "One.md",
        "transport_branch": "autoscribe/run/flight-one",
        "run_identity": "flight-one",
        "download_status": "would_download",
    }]


def test_retrieve_results_skips_downloaded_unless_forced(tmp_path: Path, monkeypatch) -> None:
    _git(tmp_path, "init", "-b", "master")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README").write_text("root\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "root")
    _flight(tmp_path, "autoscribe/run/flight-one", [{"identity": "cnt.one", "source_path": "One.md"}])
    monkeypatch.setenv("AUTOSCRIBE_HOME", str(tmp_path / "state"))

    calls: list[list[str]] = []

    def fake_run(command, *, cwd, **kwargs):
        calls.append(command)
        return SimpleNamespace(
            stdout=json.dumps({"record_identity": "cnt.one", "content": "Result", "result_identity": "result-1"}) + "\n",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr("obs.retrieval.autoscribe_bin", lambda: "asc")
    monkeypatch.setattr("obs.retrieval.run", fake_run)

    first = retrieve_results(tmp_path)
    second = retrieve_results(tmp_path)
    forced = retrieve_results(tmp_path, force=True)

    assert first[0]["download_status"] == "downloaded"
    assert second == [{
        "record_identity": "cnt.one",
        "source_path": "One.md",
        "transport_branch": "autoscribe/run/flight-one",
        "run_identity": "flight-one",
        "download_status": "already_downloaded",
    }]
    assert forced[0]["download_status"] == "downloaded"
    assert calls == [
        ["asc", "export", "extract-selected", "cnt.one"],
        ["asc", "export", "extract-selected", "cnt.one"],
    ]
