from pathlib import Path

import pytest

from code_archaeology.analyze import write_payload, write_share_snippet
from code_archaeology.utils import ArchaeologyError


def _minimal_payload() -> dict:
    return {
        "schema_version": "1.2.1",
        "summary": {
            "repo_path": "repo",
            "head_commit": "abcdef1",
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
            "since_days": 1,
            "total_commits": 0,
        },
        "settings": {
            "min_churn_threshold": 1,
            "include_authors": False,
            "include_repo_path": False,
            "include_commit_messages": False,
            "max_commits": 1,
            "max_files_per_commit": 2,
            "timeout_seconds": 1,
            "top_actions": 1,
            "use_default_ignores": True,
            "large_commit_strategy": "cap",
            "adaptive_mode": "disabled",
            "adaptive_baseline_artifact": None,
        },
        "notices": [],
        "run_metadata": {
            "tool": "cak scan",
            "tool_version": "0.0.0",
            "schema_path": "config/schemas/archaeology.schema.json",
            "truncated": False,
            "runtime_ms": 0,
            "ignore_rules_applied": [],
            "adaptive_precision": {
                "mode": "disabled",
                "strategy_version": "v1",
                "baseline_available": False,
                "baseline_source": None,
                "baseline_reason": "adaptive_disabled",
                "settings_fingerprint": "000000000000000000000000",
                "baseline_schema_version": None,
                "baseline_head_commit": None,
            },
        },
        "detectors": {
            "abandoned_structures": [],
            "temporal_coupling": {
                "pairs": [],
                "skipped_large_commits": 0,
                "capped_large_commits": 0,
                "max_files_per_commit": 2,
            },
            "era_segmentation": [],
        },
        "base_metrics": {
            "file_churn": [],
            "file_growth": [],
            "commit_themes": {},
            "recent_refactors": [],
            "time_buckets": [],
            "language_breakdown": [],
        },
        "dig_plan": [],
        "actionability": {"top_actions": [], "shadow_top_actions": [], "adaptive_changes": []},
        "errors": [],
    }


def test_write_payload_rejects_unknown_format(tmp_path: Path) -> None:
    with pytest.raises(ArchaeologyError):
        write_payload(_minimal_payload(), tmp_path, fmt="yaml", force=False)  # type: ignore[arg-type]


def test_write_payload_rejects_directory_target_before_writing_other_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_report.md").mkdir()

    with pytest.raises(ArchaeologyError, match="Output path is a directory"):
        write_payload(_minimal_payload(), out, fmt="both", force=True)

    assert not (out / "archaeology.json").exists()


def test_write_share_snippet_rejects_directory_target(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_share.md").mkdir()

    with pytest.raises(ArchaeologyError, match="Output path is a directory"):
        write_share_snippet(_minimal_payload(), out, force=True)


def test_write_share_snippet_directory_target_errors_even_without_force(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_share.md").mkdir()

    with pytest.raises(ArchaeologyError, match="Output path is a directory"):
        write_share_snippet(_minimal_payload(), out, force=False)


def test_write_payload_directory_target_errors_even_without_force(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_report.md").mkdir()

    with pytest.raises(ArchaeologyError, match="Output path is a directory"):
        write_payload(_minimal_payload(), out, fmt="md", force=False)


def test_write_payload_rolls_back_existing_outputs_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "archaeology.json"
    md_path = out / "archaeology_report.md"
    json_path.write_text("old-json\n", encoding="utf-8")
    md_path.write_text("old-md\n", encoding="utf-8")

    original_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> Path:
        if self.name.startswith("archaeology_report.md.tmp.") and target.name == "archaeology_report.md":
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    with pytest.raises(ArchaeologyError):
        write_payload(_minimal_payload(), out, fmt="both", force=True)

    assert json_path.read_text(encoding="utf-8") == "old-json\n"
    assert md_path.read_text(encoding="utf-8") == "old-md\n"
    leftovers = [p.name for p in out.iterdir() if ".tmp." in p.name or ".bak." in p.name]
    assert leftovers == []


def test_write_payload_cleans_new_outputs_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "archaeology.json"
    md_path = out / "archaeology_report.md"

    original_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> Path:
        if self.name.startswith("archaeology_report.md.tmp.") and target.name == "archaeology_report.md":
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    with pytest.raises(ArchaeologyError):
        write_payload(_minimal_payload(), out, fmt="both", force=True)

    assert not json_path.exists()
    assert not md_path.exists()
    leftovers = [p.name for p in out.iterdir() if ".tmp." in p.name or ".bak." in p.name]
    assert leftovers == []
