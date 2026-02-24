import json
import os
import subprocess
import sys
from pathlib import Path


def _env_with_pythonpath(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    return env


def _write_report(path: Path, generated_at: str) -> None:
    payload = {
        "summary": {"generated_at_utc": generated_at},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {
                        "file_a": "a.py",
                        "file_b": "b.py",
                        "coupling_ratio": 0.5,
                        "co_change_commits": 2,
                        "coupling_class": "risky",
                    }
                ]
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cli_diff_writes_markdown_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"
    out = tmp_path / "out"
    _write_report(old_json, "time1")
    _write_report(new_json, "time2")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "diff",
            "--old",
            str(old_json),
            "--new",
            str(new_json),
            "--output",
            str(out),
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (out / "archaeology_diff.md").exists()


def test_cli_diff_rejects_output_path_when_it_is_a_file(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"
    _write_report(old_json, "time1")
    _write_report(new_json, "time2")
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("x", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "diff",
            "--old",
            str(old_json),
            "--new",
            str(new_json),
            "--output",
            str(output_file),
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Output path is a file" in result.stderr
