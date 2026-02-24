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


def test_scan_json_mode_emits_structured_error_for_validation_failures(tmp_path: Path) -> None:
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
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema"] == "cak.scan.v1"
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "--ack-pii" in payload["errors"][0]["message"]


def test_scan_json_mode_preserves_written_artifact_paths_when_share_snippet_fails(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")
    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_events.jsonl").mkdir()

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

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["artifacts"]["json"] == str(out / "archaeology.json")
    assert payload["artifacts"]["markdown"] == str(out / "archaeology_report.md")
    assert payload["share"]["snippet_markdown"] == str(out / "archaeology_share.md")
    assert payload["share"]["events_jsonl"] is None
    assert (out / "archaeology.json").exists()
    assert (out / "archaeology_report.md").exists()
    assert (out / "archaeology_share.md").exists()
    assert "Failed to write file" in payload["errors"][0]["message"]


def test_include_authors_with_ack_pii_emits_author_activity(tmp_path: Path) -> None:
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
            "--format",
            "json",
            "--force",
            "--include-authors",
            "--ack-pii",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "archaeology.json").read_text())
    assert payload["settings"]["include_authors"] is True
    assert payload["base_metrics"]["author_activity"][0]["author"].startswith("Test User <")


def test_scan_supports_sha256_git_repositories(tmp_path: Path) -> None:
    import pytest

    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    try:
        subprocess.run(
            ["git", "init", "--object-format=sha256", str(repo)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        pytest.skip("git does not support --object-format=sha256 on this system")

    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "a.py").write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", "src/a.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add a"], check=True, capture_output=True, text=True)

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
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "archaeology.json").read_text())
    assert len(payload["summary"]["head_commit"]) == 64


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


def test_default_ignores_filter_nested_dist_and_build_directories(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")
    _commit(repo, "packages/web/dist/bundle.js", "console.log(1)\n", "chore: dist output")
    _commit(repo, "services/api/build/output.txt", "artifact\n", "chore: build output")
    _commit(repo, "apps/mobile/poetry.lock", "lock\n", "chore: lockfile")

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
    assert "packages/web/dist/bundle.js" not in churn_files
    assert "services/api/build/output.txt" not in churn_files
    assert "apps/mobile/poetry.lock" not in churn_files


def test_default_ignores_apply_after_rename_normalization(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")
    subprocess.run(["git", "-C", str(repo), "mv", "src/a.py", "src/poetry.lock"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "chore: rename to lock"], check=True, capture_output=True, text=True)

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
    assert "src/poetry.lock" not in churn_files


def test_scan_share_snippet_fails_before_writing_when_share_exists(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")

    # Seed existing share file only.
    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_share.md").write_text("existing\n")

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
            "--share-snippet",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Refusing overwrite" in result.stderr
    assert not (out / "archaeology.json").exists()


def test_scan_share_snippet_json_mode_emits_structured_preflight_error(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")

    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_share.md").write_text("existing\n")

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
            "--share-snippet",
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "Refusing overwrite" in payload["errors"][0]["message"]
    assert not (out / "archaeology.json").exists()


def test_scan_share_snippet_json_mode_reports_directory_target_error(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")

    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_share.md").mkdir()

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
            "--share-snippet",
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "Output path is a directory" in payload["errors"][0]["message"]


def test_scan_share_snippet_json_mode_reports_directory_target_error_even_with_force(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out = tmp_path / "out"

    _init_repo(repo)
    _commit(repo, "src/a.py", "print(1)\n", "feat: add a")

    out.mkdir(parents=True, exist_ok=True)
    (out / "archaeology_share.md").mkdir()

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
            "--share-snippet",
            "--json",
            "--force",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "Output path is a directory" in payload["errors"][0]["message"]
    assert not (out / "archaeology.json").exists()


def test_scan_empty_repository_returns_clear_error(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    _init_repo(repo)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Repository has no commits to analyze" in result.stderr


def test_scan_json_mode_emits_structured_error_for_runtime_failures(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    _init_repo(repo)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema"] == "cak.scan.v1"
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "Repository has no commits to analyze" in payload["errors"][0]["message"]


def test_scan_rejects_non_positive_timeout(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
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
            "--timeout-seconds",
            "0",
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "--timeout-seconds must be >= 1" in payload["errors"][0]["message"]


def test_scan_json_mode_emits_structured_error_when_output_dir_is_file(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out_file = tmp_path / "not_a_dir"

    _init_repo(repo)
    _commit(repo, "README.md", "x\n", "docs: init")
    out_file.write_text("occupied\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
            "--output-dir",
            str(out_file),
            "--json",
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SCAN_ERROR"
    assert "output directory" in payload["errors"][0]["message"].lower()


def test_scan_human_mode_reports_output_dir_file_error_without_traceback(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    out_file = tmp_path / "not_a_dir"

    _init_repo(repo)
    _commit(repo, "README.md", "x\n", "docs: init")
    out_file.write_text("occupied\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "code_archaeology",
            "scan",
            "--repo",
            str(repo),
            "--output-dir",
            str(out_file),
        ],
        cwd=root,
        env=_env_with_pythonpath(root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
