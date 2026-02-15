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
    # Test stability: disable any global commit signing hooks (e.g. 1Password/GPG) that can break in CI/headless runs.
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "tag.gpgsign", "false"], check=True)


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
    assert "--include-repo-path" in result.stdout
    assert "--include-commit-messages" in result.stdout
    assert "--large-commit-strategy" in result.stdout
    assert "--share-snippet" in result.stdout


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
            "--share-snippet",
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    wrapper = json.loads(result.stdout)
    assert wrapper["share"]["snippet_markdown"] is not None
    assert wrapper["share"]["events_jsonl"] is not None
    payload = json.loads((out / "archaeology.json").read_text())
    assert payload["schema_version"] == "1.2.0"
    assert payload["summary"]["repo_path"] == "repo"
    assert isinstance(payload["notices"], list)
    assert len(payload["actionability"]["top_actions"]) == 2
    assert "ignore_rules_applied" in payload["run_metadata"]
    assert (out / "archaeology_report.md").exists()
    assert (out / "archaeology_share.md").exists()
    assert (out / "archaeology_events.jsonl").exists()


def test_redaction_defaults_and_include_flags(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")
    _commit(repo, "src/a.py", "print(2)\n", "refactor: improve a")

    # Defaults: repo path and commit messages are redacted.
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
            "--format",
            "json",
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
    assert payload["summary"]["repo_path"] == "repo"
    assert any(n["code"] == "REPO_PATH_REDACTED" for n in payload["notices"])
    assert any(n["code"] == "COMMIT_MESSAGES_REDACTED" for n in payload["notices"])
    assert payload["base_metrics"]["recent_refactors"][0]["message"] == "<redacted>"
    assert payload["base_metrics"]["recent_refactors"][0]["message_redacted"] is True

    # Opt-in: include full repo path and commit messages.
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
            "--format",
            "json",
            "--force",
            "--json",
            "--include-repo-path",
            "--include-commit-messages",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "archaeology.json").read_text())
    assert payload["summary"]["repo_path"] == str(repo.resolve())
    assert all(n["code"] != "REPO_PATH_REDACTED" for n in payload["notices"])
    assert all(n["code"] != "COMMIT_MESSAGES_REDACTED" for n in payload["notices"])
    assert payload["base_metrics"]["recent_refactors"][0]["message"].startswith("refactor:")
    assert payload["base_metrics"]["recent_refactors"][0]["message_redacted"] is False


def test_large_commit_capping_emits_notice(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    # One large commit touching many files.
    for idx in range(7):
        path = repo / f"src/f{idx}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"print({idx})\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: big change"], check=True, capture_output=True, text=True)

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
            "--format",
            "json",
            "--force",
            "--max-files-per-commit",
            "2",
            "--large-commit-strategy",
            "cap",
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
    assert payload["detectors"]["temporal_coupling"]["capped_large_commits"] == 1
    assert any(n["code"] == "TEMPORAL_COUPLING_CAPPED" for n in payload["notices"])


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
