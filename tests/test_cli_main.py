import json
import sys
from pathlib import Path

from code_archaeology.cli import main
from code_archaeology.utils import ArchaeologyError


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


def test_main_scan_json_mode_preserves_payload_context_on_post_scan_failure(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    out = tmp_path / "out"
    repo.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    fake_payload = {
        "actionability": {"top_actions": [{"action": "review_temporal_coupling"}]},
        "notices": [{"code": "REPO_PATH_REDACTED", "message": "redacted"}],
        "errors": [{"code": "PREVIOUS_WARNING", "message": "something"}],
    }

    def _fake_analyze(**_: object) -> dict:
        return fake_payload

    def _fake_write_payload(*_: object, **__: object) -> tuple[Path, Path]:
        return out / "archaeology.json", out / "archaeology_report.md"

    def _fail_share(*_: object, **__: object) -> Path:
        raise ArchaeologyError("share snippet failed")

    monkeypatch.setattr("code_archaeology.cli.analyze_repo", _fake_analyze)
    monkeypatch.setattr("code_archaeology.cli.write_payload", _fake_write_payload)
    monkeypatch.setattr("code_archaeology.cli.write_share_snippet", _fail_share)
    monkeypatch.setattr(
        sys,
        "argv",
        ["cak", "scan", "--repo", str(repo), "--output-dir", str(out), "--share-snippet", "--json"],
    )

    code = main()
    captured = capsys.readouterr()

    assert code == 2
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["artifacts"]["json"] == str(out / "archaeology.json")
    assert payload["artifacts"]["markdown"] == str(out / "archaeology_report.md")
    assert payload["top_actions"] == fake_payload["actionability"]["top_actions"]
    assert payload["notices"] == fake_payload["notices"]
    assert payload["errors"][0]["code"] == "PREVIOUS_WARNING"
    assert payload["errors"][-1]["code"] == "SCAN_ERROR"
    assert "share snippet failed" in payload["errors"][-1]["message"]
