from code_archaeology.metrics import temporal_coupling
from code_archaeology.models import Commit, FileChange
import pytest


def _commit(commit_hash: str, files: list[str]) -> Commit:
    return Commit(
        hash=commit_hash,
        date="2026-01-01T00:00:00+00:00",
        author_name="Test User",
        author_email="test@example.com",
        message="test commit",
        files=[FileChange(path=f, additions=1, deletions=0) for f in files],
    )


def test_temporal_coupling_skip_excludes_large_commit_from_denominator(tmp_path):
    repo = tmp_path
    commits = [
        _commit("a" * 40, ["src/a.py", "src/b.py", "src/c.py"]),  # skipped
        _commit("b" * 40, ["src/a.py", "src/b.py"]),  # counted
    ]

    out = temporal_coupling(
        repo_path=repo,
        commits=commits,
        min_co_changes=1,
        max_files_per_commit=2,
        large_commit_strategy="skip",
    )

    pair = next((p for p in out["pairs"] if {p["file_a"], p["file_b"]} == {"src/a.py", "src/b.py"}), None)
    assert pair is not None
    assert pair["coupling_ratio"] == 1.0


def test_temporal_coupling_reuses_import_parsing_for_shared_files(tmp_path, monkeypatch):
    repo = tmp_path
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "infra").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "a.py").write_text("import infra.b\n")
    (repo / "infra" / "b.py").write_text("import src.c\n")
    (repo / "src" / "c.py").write_text("VALUE = 1\n")

    commits = [
        _commit("a" * 40, ["src/a.py", "infra/b.py", "src/c.py"]),
        _commit("b" * 40, ["src/a.py", "infra/b.py", "src/c.py"]),
    ]

    from code_archaeology import ast_coupling

    original = ast_coupling.extract_python_imports
    calls: list[str] = []

    def wrapped(path):
        calls.append(str(path))
        return original(path)

    monkeypatch.setattr(ast_coupling, "extract_python_imports", wrapped)

    temporal_coupling(
        repo_path=repo,
        commits=commits,
        min_co_changes=1,
        max_files_per_commit=10,
        large_commit_strategy="cap",
    )

    # Without caching this is 4+ reads for this 3-file, 2-pair scenario.
    assert len(calls) <= 3


def test_temporal_coupling_rejects_invalid_large_commit_strategy(tmp_path):
    repo = tmp_path
    commits = [_commit("a" * 40, ["src/a.py", "src/b.py"])]

    with pytest.raises(ValueError):
        temporal_coupling(
            repo_path=repo,
            commits=commits,
            min_co_changes=1,
            max_files_per_commit=2,
            large_commit_strategy="truncate",
        )


def test_temporal_coupling_rejects_invalid_limits(tmp_path):
    repo = tmp_path
    commits = [_commit("a" * 40, ["src/a.py", "src/b.py"])]

    with pytest.raises(ValueError):
        temporal_coupling(
            repo_path=repo,
            commits=commits,
            min_co_changes=0,
            max_files_per_commit=2,
            large_commit_strategy="cap",
        )

    with pytest.raises(ValueError):
        temporal_coupling(
            repo_path=repo,
            commits=commits,
            min_co_changes=1,
            max_files_per_commit=1,
            large_commit_strategy="cap",
        )
