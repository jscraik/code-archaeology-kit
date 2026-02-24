from pathlib import Path
import subprocess

from code_archaeology.git import parse_git_log


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "tag.gpgsign", "false"], check=True)


def test_parse_git_log_handles_pipe_in_file_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "src" / "a|b.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("print(1)\\n")

    subprocess.run(["git", "-C", str(repo), "add", str(file_path.relative_to(repo))], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add weird path"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert len(commits) == 1
    assert [f.path for f in commits[0].files] == ["src/a|b.py"]


def test_parse_git_log_decodes_quoted_tab_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "a\tb.py"
    file_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add tab path"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert len(commits) == 1
    assert [f.path for f in commits[0].files] == ["a\tb.py"]


def test_parse_git_log_decodes_quoted_utf8_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "café.py"
    file_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add unicode path"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert len(commits) == 1
    assert [f.path for f in commits[0].files] == ["café.py"]


def test_parse_git_log_preserves_literal_backslash_in_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "a\\b.py"
    file_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add backslash path"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert len(commits) == 1
    assert [f.path for f in commits[0].files] == ["a\\b.py"]


def test_parse_git_log_preserves_leading_and_trailing_spaces_in_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / " leading and trailing .py "
    file_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add spaced path"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert len(commits) == 1
    assert [f.path for f in commits[0].files] == [" leading and trailing .py "]


def test_parse_git_log_handles_pipe_in_author_and_message(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Name|WithPipe"], check=True)

    file_path = repo / "src" / "a.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("print(1)\n")

    subprocess.run(["git", "-C", str(repo), "add", str(file_path.relative_to(repo))], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: message | with pipe"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert len(commits) == 1
    assert commits[0].author_name == "Name|WithPipe"
    assert commits[0].message == "feat: message | with pipe"


def test_parse_git_log_normalizes_rename_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    src = repo / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "old.py").write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", "src/old.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "src/old.py", "src/new.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename file"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename"))
    assert [f.path for f in rename_commit.files] == ["src/new.py"]


def test_parse_git_log_preserves_literal_brace_arrow_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "x{a => b}y.txt"
    file_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add literal brace arrow filename"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert [f.path for f in commits[0].files] == ["x{a => b}y.txt"]


def test_parse_git_log_preserves_literal_arrow_in_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "a => b.txt"
    file_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add literal arrow filename"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert [f.path for f in commits[0].files] == ["a => b.txt"]


def test_parse_git_log_normalizes_root_rename_without_braces(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "old.py"
    old_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add root file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "old.py", "new.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename root file"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename root"))
    assert [f.path for f in rename_commit.files] == ["new.py"]


def test_parse_git_log_normalizes_root_rename_with_edits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "old.py"
    old_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add root file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "old.py", "new.py"], check=True)
    (repo / "new.py").write_text("print(1)\nprint(2)\n")
    subprocess.run(["git", "-C", str(repo), "add", "new.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename root file with edit"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename root file with edit"))
    assert [f.path for f in rename_commit.files] == ["new.py"]


def test_parse_git_log_normalizes_quoted_root_rename_with_tab_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "a\tb.py"
    new_path = repo / "c\td.py"
    old_path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add tab file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", old_path.name, new_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename tab file"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename tab file"))
    assert [f.path for f in rename_commit.files] == ["c\td.py"]


def test_parse_git_log_max_commits_applies_even_when_commits_are_fully_ignored(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    cache_dir = repo / "__pycache__"
    cache_dir.mkdir(parents=True, exist_ok=True)

    (cache_dir / "a.pyc").write_text("a\n")
    subprocess.run(["git", "-C", str(repo), "add", "__pycache__/a.pyc"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "chore: cache 1"], check=True, capture_output=True, text=True)

    (cache_dir / "a.pyc").write_text("b\n")
    subprocess.run(["git", "-C", str(repo), "add", "__pycache__/a.pyc"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "chore: cache 2"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(
        repo=repo,
        since_days=365,
        timeout_seconds=30,
        max_commits=1,
        ignore_globs=["__pycache__/**"],
    )

    assert commits == []
    assert truncated is True


def test_parse_git_log_normalizes_rename_from_literal_arrow_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "a => b.txt"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add literal arrow"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "a => b.txt", "c.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename from literal arrow"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename from literal arrow"))
    assert [f.path for f in rename_commit.files] == ["c.txt"]


def test_parse_git_log_normalizes_rename_to_literal_arrow_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "old.py"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add root file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "old.py", "a => b.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename to literal arrow"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename to literal arrow"))
    assert [f.path for f in rename_commit.files] == ["a => b.txt"]


def test_parse_git_log_normalizes_rename_to_literal_arrow_filename_with_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "old.py"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add root file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "old.py", "a => b.txt"], check=True)
    (repo / "a => b.txt").write_text("x\ny\n")
    subprocess.run(["git", "-C", str(repo), "add", "a => b.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename to literal arrow with edit"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename to literal arrow with edit"))
    assert [f.path for f in rename_commit.files] == ["a => b.txt"]


def test_parse_git_log_resolves_ambiguous_root_rename_with_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "a => b.txt"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add literal arrow"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "a => b.txt", "c => d.txt"], check=True)
    (repo / "c => d.txt").write_text("x\ny\n")
    subprocess.run(["git", "-C", str(repo), "add", "c => d.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: ambiguous root rename with edit"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: ambiguous root rename with edit"))
    assert [f.path for f in rename_commit.files] == ["c => d.txt"]


def test_parse_git_log_preserves_literal_brace_arrow_target_in_root_rename_with_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "old.py"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add root file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "old.py", "left {a => b}.txt"], check=True)
    (repo / "left {a => b}.txt").write_text("x\ny\n")
    subprocess.run(["git", "-C", str(repo), "add", "left {a => b}.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "refactor: rename to literal brace arrow with edit"],
        check=True,
        capture_output=True,
        text=True,
    )

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename to literal brace arrow with edit"))
    assert [f.path for f in rename_commit.files] == ["left {a => b}.txt"]


def test_parse_git_log_preserves_literal_brace_arrow_source_in_root_rename_with_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "left {a => b}.txt"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add literal brace arrow file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "left {a => b}.txt", "new.py"], check=True)
    (repo / "new.py").write_text("x\ny\n")
    subprocess.run(["git", "-C", str(repo), "add", "new.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "refactor: rename from literal brace arrow with edit"],
        check=True,
        capture_output=True,
        text=True,
    )

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename from literal brace arrow with edit"))
    assert [f.path for f in rename_commit.files] == ["new.py"]


def test_parse_git_log_resolves_overlapping_root_rename_delimiter_without_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "a =>"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "--", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add overlapping rename source"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "--", "a =>", "=> b.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "refactor: overlapping delimiter rename"],
        check=True,
        capture_output=True,
        text=True,
    )

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: overlapping delimiter rename"))
    assert [f.path for f in rename_commit.files] == ["=> b.txt"]


def test_parse_git_log_resolves_overlapping_root_rename_delimiter_with_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    old_path = repo / "a =>"
    old_path.write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "--", old_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add overlapping rename source"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "--", "a =>", "=> b.txt"], check=True)
    (repo / "=> b.txt").write_text("x\ny\n")
    subprocess.run(["git", "-C", str(repo), "add", "--", "=> b.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "refactor: overlapping delimiter rename with edit"],
        check=True,
        capture_output=True,
        text=True,
    )

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: overlapping delimiter rename with edit"))
    assert [f.path for f in rename_commit.files] == ["=> b.txt"]


def test_parse_git_log_applies_ignore_globs_after_rename_normalization(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "a.py").write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", "src/a.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add python file"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "src/a.py", "src/poetry.lock"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "chore: rename to lockfile"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(
        repo=repo,
        since_days=365,
        timeout_seconds=30,
        max_commits=100,
        ignore_globs=["**/*.lock"],
    )

    assert truncated is False
    messages = [c.message for c in commits]
    assert "chore: rename to lockfile" not in messages


def test_parse_git_log_preserves_long_paths_without_truncation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    parts = ["d" * 30 for _ in range(28)]
    rel = "/".join(parts) + "/file.py"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print(1)\n")
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add long path"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    assert [f.path for f in commits[0].files] == [rel]


def test_parse_git_log_resolves_ambiguous_rename_when_other_candidate_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "a => b.txt").write_text("a\n")
    (repo / "b.txt => c.txt").write_text("b\n")
    subprocess.run(["git", "-C", str(repo), "add", "a => b.txt", "b.txt => c.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: seed files"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "a => b.txt", "c.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: ambiguous rename"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: ambiguous rename"))
    assert [f.path for f in rename_commit.files] == ["c.txt"]


def test_parse_git_log_does_not_misclassify_mode_change_as_rename_for_literal_arrow_name(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    file_path = repo / "a => b.sh"
    file_path.write_text("echo hi\n")
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add script"], check=True, capture_output=True, text=True)

    file_path.chmod(0o755)
    subprocess.run(["git", "-C", str(repo), "add", file_path.name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "chore: chmod script"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    mode_change_commit = next(c for c in commits if c.message.startswith("chore: chmod script"))
    assert [f.path for f in mode_change_commit.files] == ["a => b.sh"]


def test_parse_git_log_prefers_rename_target_when_ambiguous_split_source_was_deleted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "a").write_text("old\n")
    (repo / "a => b").write_text("ambiguous-source\n")
    (repo / "c.txt").write_text("existing-target2\n")
    subprocess.run(["git", "-C", str(repo), "add", "a", "a => b", "c.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: seed files"], check=True, capture_output=True, text=True)

    subprocess.run(["git", "-C", str(repo), "mv", "a", "b => c.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "rm", "a => b"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "refactor: rename with delete"], check=True, capture_output=True, text=True)

    commits, truncated = parse_git_log(repo=repo, since_days=365, timeout_seconds=30, max_commits=100, ignore_globs=[])

    assert truncated is False
    rename_commit = next(c for c in commits if c.message.startswith("refactor: rename with delete"))
    assert [f.path for f in rename_commit.files] == ["a => b", "b => c.txt"]
