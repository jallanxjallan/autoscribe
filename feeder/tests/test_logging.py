from __future__ import annotations

from pathlib import Path

from obs.cli import parser
from obs.logging import read_log, write_log


def test_log_parser_defaults() -> None:
    args = parser().parse_args(["log"])
    assert args.command == "log"
    assert args.date is None
    assert args.lines == 200


def test_daily_log_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOSCRIBE_HOME", str(tmp_path / "state"))
    vault = tmp_path / "vault"
    vault.mkdir()

    write_log(vault, "dispatch-run", "started: branch=autoscribe/run/test")
    write_log(vault, "dispatch-run", "completed: 1 record(s)\ncnt.test Contents/Test.md")

    text = read_log(vault, lines=20)
    assert "dispatch-run: started: branch=autoscribe/run/test" in text
    assert "dispatch-run: completed: 1 record(s)" in text
    assert "cnt.test Contents/Test.md" in text
