import json
import os
import subprocess
import sys
from pathlib import Path


def _env_with_pythonpath(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    return env


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)


def _commit(repo: Path, rel: str, content: str, message: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True, text=True)


def test_scan_help() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "code_archaeology", "scan", "--help"],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--repo" in result.stdout
    assert "--ignore-glob" in result.stdout


def test_schema_valid_json() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = root / "config" / "schemas" / "archaeology.schema.json"
    data = json.loads(schema.read_text())
    assert data["type"] == "object"
    assert "actionability" in data["properties"]


def test_scan_generates_contract_and_top_actions(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")
    _commit(repo, "src/a.py", "print(2)\n", "fix: update a")
    _commit(repo, "tests/test_a.py", "def test_x(): pass\n", "test: add test")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
            "--output-dir",
            str(out),
            "--top-actions",
            "2",
            "--format",
            "both",
            "--force",
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "archaeology.json").read_text())
    assert payload["schema_version"] == "1.1.0"
    assert len(payload["actionability"]["top_actions"]) == 2
    assert "ignore_rules_applied" in payload["run_metadata"]
    assert (out / "archaeology_report.md").exists()


def test_include_authors_requires_ack_pii(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "README.md", "x\n", "docs: init")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
            "--output-dir",
            str(out),
            "--include-authors",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--ack-pii" in result.stderr


def test_ignore_glob_filters_generated_noise(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")
    _commit(repo, "__pycache__/a.pyc", "bin\n", "chore: add cache")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
            "--output-dir",
            str(out),
            "--ignore-glob",
            "__pycache__/**",
            "--format",
            "json",
            "--force",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "archaeology.json").read_text())
    churn_files = {row["file"] for row in payload["base_metrics"]["file_churn"]}
    assert all("__pycache__" not in path for path in churn_files)
