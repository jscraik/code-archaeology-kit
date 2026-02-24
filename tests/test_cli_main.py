import json
import sys
from pathlib import Path

from code_archaeology.cli import main


def test_main_scan_json_mode_wraps_unexpected_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    def _boom(**_: object) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("code_archaeology.cli.analyze_repo", _boom)
    monkeypatch.setattr(sys, "argv", ["cak", "scan", "--repo", str(repo), "--json"])

    code = main()
    captured = capsys.readouterr()

    assert code == 2
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "Unexpected internal error: boom" in payload["errors"][0]["message"]


def test_main_scan_text_mode_wraps_unexpected_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    def _boom(**_: object) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("code_archaeology.cli.analyze_repo", _boom)
    monkeypatch.setattr(sys, "argv", ["cak", "scan", "--repo", str(repo)])

    code = main()
    captured = capsys.readouterr()

    assert code == 2
    assert captured.out == ""
    assert "error: Unexpected internal error: boom" in captured.err
