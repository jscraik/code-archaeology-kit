import subprocess
from pathlib import Path

import pytest

from code_archaeology.analyze import analyze_repo
from code_archaeology.utils import ArchaeologyError


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "tag.gpgsign", "false"], check=True)


def _commit(repo: Path, rel: str, content: str, message: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True, text=True)


def test_analyze_repo_wraps_schema_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")

    def _boom(payload: dict, schema_path: Path) -> None:
        raise RuntimeError("schema exploded")

    monkeypatch.setattr("code_archaeology.analyze._validate_payload_schema", _boom)

    with pytest.raises(ArchaeologyError, match="Schema validation failed"):
        analyze_repo(
            repo=repo,
            since_days=365,
            min_churn_threshold=1,
            include_authors=False,
            include_repo_path=False,
            include_commit_messages=False,
            timeout_seconds=30,
            max_commits=100,
            max_files_per_commit=40,
            version="0.0.0",
            ignore_globs=[],
            use_default_ignores=True,
            top_actions=3,
            large_commit_strategy="cap",
        )
