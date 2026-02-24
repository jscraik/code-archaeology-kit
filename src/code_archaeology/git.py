from __future__ import annotations
import subprocess
import time
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from .models import Commit, FileChange

from .utils import ArchaeologyError, sanitize, sanitize_path, matches_any

COMMIT_PREFIX = "__CAK_COMMIT__"
COMMIT_FIELD_SEP = "\x1f"
RENAME_COMPACT_BRACE_RE = re.compile(r"^(?P<prefix>[^{}]*)\{(?P<old>[^{}]+) => (?P<new>[^{}]+)\}(?P<suffix>[^{}]*)$")
RENAME_SUMMARY_RE = re.compile(r"^rename (.+) \(\d+%\)$")
QUOTED_PATH_TOKEN_RE = re.compile(r'"(?:\\.|[^"])*"')


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _decode_git_c_escaped(text: str) -> str:
    out = bytearray()
    i = 0
    escapes = {
        "a": 0x07,
        "b": 0x08,
        "f": 0x0C,
        "n": 0x0A,
        "r": 0x0D,
        "t": 0x09,
        "v": 0x0B,
        "\\": 0x5C,
        '"': 0x22,
    }

    while i < len(text):
        ch = text[i]
        if ch != "\\":
            out.extend(ch.encode("utf-8"))
            i += 1
            continue

        i += 1
        if i >= len(text):
            out.append(0x5C)
            break

        esc = text[i]
        if esc in "01234567":
            oct_digits = esc
            i += 1
            for _ in range(2):
                if i < len(text) and text[i] in "01234567":
                    oct_digits += text[i]
                    i += 1
                else:
                    break
            out.append(int(oct_digits, 8))
            continue

        code = escapes.get(esc)
        if code is not None:
            out.append(code)
        else:
            out.extend(esc.encode("utf-8"))
        i += 1

    return out.decode("utf-8", errors="replace")


def _decode_git_quoted_tokens(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return _decode_git_c_escaped(token[1:-1])

    return QUOTED_PATH_TOKEN_RE.sub(repl, value)


def _normalize_numstat_path(
    path: str,
    additions: str,
    deletions: str,
    root_rename_hints: set[str] | None = None,
) -> str:
    normalized = _decode_git_quoted_tokens(path)
    if " => " not in normalized:
        return normalized

    if root_rename_hints and normalized in root_rename_hints:
        compact_match = RENAME_COMPACT_BRACE_RE.match(normalized)
        if compact_match:
            prefix = compact_match.group("prefix")
            suffix = compact_match.group("suffix")
            if " => " not in f"{prefix}{suffix}":
                return f"{prefix}{compact_match.group('new')}{suffix}"
        split_candidates = _ambiguous_rename_splits(normalized)
        if len(split_candidates) == 1:
            return split_candidates[0][1]
        return normalized

    return normalized


def _ambiguous_rename_splits(rename_spec: str) -> list[tuple[str, str]]:
    delimiter = " => "
    out: list[tuple[str, str]] = []
    idx = 0
    while True:
        split_at = rename_spec.find(delimiter, idx)
        if split_at < 0:
            break
        source = rename_spec[:split_at]
        target = rename_spec[split_at + len(delimiter) :]
        if source and target:
            out.append((source, target))
        idx = split_at + 1
    return out


def _path_exists_at_commit(
    repo: Path,
    commitish: str,
    path: str,
    timeout: int,
    cache: dict[tuple[str, str], bool],
) -> bool:
    key = (commitish, path)
    if key in cache:
        return cache[key]

    cmd = ["git", "-C", str(repo), "cat-file", "-e", f"{commitish}:{path}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        cache[key] = False
        return False

    exists = result.returncode == 0
    cache[key] = exists
    return exists


def _parent_commit(
    repo: Path,
    commit_hash: str,
    timeout: int,
    cache: dict[str, str | None],
) -> str | None:
    if commit_hash in cache:
        return cache[commit_hash]

    cmd = ["git", "-C", str(repo), "rev-parse", "--verify", f"{commit_hash}^"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        cache[commit_hash] = None
        return None

    if result.returncode == 0:
        parent = result.stdout.strip() or None
        cache[commit_hash] = parent
        return parent

    cache[commit_hash] = None
    return None


def _resolve_ambiguous_rename_target(
    repo: Path,
    commit_hash: str,
    rename_spec: str,
    timeout_seconds: int,
    cache: dict[str, str],
    existence_cache: dict[tuple[str, str], bool],
    parent_cache: dict[str, str | None],
    nonzero_paths: set[str] | None = None,
) -> str | None:
    cache_key = f"{commit_hash}:{rename_spec}"
    if cache_key in cache:
        return cache[cache_key] or None

    timeout = max(1, min(timeout_seconds, 5))
    parent = _parent_commit(repo=repo, commit_hash=commit_hash, timeout=timeout, cache=parent_cache)

    best_target: str | None = None
    best_score: tuple[int, int] | None = None

    for source_candidate, target_candidate in _ambiguous_rename_splits(rename_spec):
        target_exists = _path_exists_at_commit(
            repo=repo,
            commitish=commit_hash,
            path=target_candidate,
            timeout=timeout,
            cache=existence_cache,
        )
        if not target_exists:
            continue

        source_exists_in_current = _path_exists_at_commit(
            repo=repo,
            commitish=commit_hash,
            path=source_candidate,
            timeout=timeout,
            cache=existence_cache,
        )
        if source_exists_in_current:
            continue

        source_exists_in_parent = False
        if parent:
            source_exists_in_parent = _path_exists_at_commit(
                repo=repo,
                commitish=parent,
                path=source_candidate,
                timeout=timeout,
                cache=existence_cache,
            )

        source_seen_as_nonzero_change = nonzero_paths is not None and source_candidate in nonzero_paths
        score = (
            1 if source_exists_in_parent else 0,
            1 if not source_seen_as_nonzero_change else 0,
            len(source_candidate),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_target = target_candidate

    if best_target is not None:
        cache[cache_key] = best_target
        return best_target

    cache[cache_key] = ""
    return None

def run_git(cmd: list[str], timeout_seconds: int) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise ArchaeologyError(f"git timed out after {timeout_seconds}s") from exc
    except subprocess.CalledProcessError as exc:
        raise ArchaeologyError(sanitize(exc.stderr or str(exc))) from exc
    except FileNotFoundError as exc:
        raise ArchaeologyError("git not found") from exc
    return result.stdout

def parse_git_log(
    repo: Path,
    since_days: int,
    timeout_seconds: int,
    max_commits: int,
    ignore_globs: list[str],
) -> tuple[list[Commit], bool]:
    since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    cmd = [
        "git",
        "-C",
        str(repo),
        "log",
        f"--since={since_date}",
        f"--pretty=format:{COMMIT_PREFIX}%H%x1f%ai%x1f%an%x1f%ae%x1f%s",
        "--numstat",
        "--summary",
    ]

    commits: list[Commit] = []
    current: dict[str, Any] | None = None
    current_root_rename_hints: set[str] = set()
    current_nonzero_paths: set[str] = set()
    ambiguous_rename_cache: dict[str, str] = {}
    existence_cache: dict[tuple[str, str], bool] = {}
    parent_cache: dict[str, str | None] = {}
    truncated = False
    seen_commit_headers = 0

    start = time.time()
    try:
        proc: subprocess.Popen[str] = subprocess.Popen(  # pyright: ignore[reportUnknownMemberType]
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ArchaeologyError("git not found") from exc

    assert proc.stdout is not None
    assert proc.stderr is not None

    try:
        for raw_line in proc.stdout:
            if time.time() - start > timeout_seconds:
                _terminate_process(proc)
                raise ArchaeologyError(f"git timed out after {timeout_seconds}s")

            line = raw_line.rstrip("\n")
            if not line:
                continue

            if line.startswith(COMMIT_PREFIX):
                if current and current["files"]:
                    commits.append(Commit(**current))

                seen_commit_headers += 1
                if seen_commit_headers > max_commits:
                    truncated = True
                    _terminate_process(proc)
                    break

                parts = line[len(COMMIT_PREFIX) :].split(COMMIT_FIELD_SEP, 4)
                if len(parts) < 5:
                    continue

                parsed_date: datetime | None = None
                date_str = parts[1]
                try:
                    parsed_date = datetime.strptime(parts[1], "%Y-%m-%d %H:%M:%S %z")
                    date_str = parsed_date.isoformat()
                except ValueError:
                    pass

                current = {
                    "hash": parts[0],
                    "date": date_str,
                    "author_name": sanitize(parts[2]),
                    "author_email": sanitize(parts[3]),
                    "message": sanitize(parts[4]),
                    "files": [],
                }
                current_root_rename_hints = set()
                current_nonzero_paths = set()
                if parsed_date is not None:
                    current["date_obj"] = parsed_date
                continue

            if current is None:
                continue

            stripped = line.strip()
            rename_match = RENAME_SUMMARY_RE.match(stripped)
            if rename_match:
                rename_spec = _decode_git_quoted_tokens(rename_match.group(1))
                current_root_rename_hints.add(rename_spec)
                normalized_target = _normalize_numstat_path(rename_spec, "0", "0", {rename_spec})
                if (
                    normalized_target == rename_spec
                    and len(_ambiguous_rename_splits(rename_spec)) > 1
                    and isinstance(current.get("hash"), str)
                ):
                    resolved = _resolve_ambiguous_rename_target(
                        repo=repo,
                        commit_hash=current["hash"],
                        rename_spec=rename_spec,
                        timeout_seconds=timeout_seconds,
                        cache=ambiguous_rename_cache,
                        existence_cache=existence_cache,
                        parent_cache=parent_cache,
                        nonzero_paths={f.path for f in current["files"] if f.additions != 0 or f.deletions != 0},
                    )
                    if resolved:
                        normalized_target = resolved
                normalized_target = sanitize_path(normalized_target)
                normalized_spec = sanitize_path(rename_spec)
                for file_change in current["files"]:
                    if file_change.path == normalized_spec:
                        file_change.path = normalized_target
                current["files"] = [file_change for file_change in current["files"] if not matches_any(file_change.path, ignore_globs)]
                current_nonzero_paths = {
                    file_change.path
                    for file_change in current["files"]
                    if file_change.additions != 0 or file_change.deletions != 0
                }
                continue

            m = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if not m:
                continue

            normalized_path = _normalize_numstat_path(m.group(3), m.group(1), m.group(2), current_root_rename_hints)
            if (
                normalized_path == _decode_git_quoted_tokens(m.group(3))
                and m.group(1) == "0"
                and m.group(2) == "0"
                and len(_ambiguous_rename_splits(normalized_path)) > 1
                and isinstance(current.get("hash"), str)
            ):
                resolved = _resolve_ambiguous_rename_target(
                    repo=repo,
                    commit_hash=current["hash"],
                    rename_spec=normalized_path,
                    timeout_seconds=timeout_seconds,
                    cache=ambiguous_rename_cache,
                    existence_cache=existence_cache,
                    parent_cache=parent_cache,
                    nonzero_paths=current_nonzero_paths,
                )
                if resolved:
                    normalized_path = resolved

            file_path = sanitize_path(normalized_path)
            additions = 0 if m.group(1) == "-" else int(m.group(1))
            deletions = 0 if m.group(2) == "-" else int(m.group(2))
            if additions != 0 or deletions != 0:
                current_nonzero_paths.add(file_path)
            if matches_any(file_path, ignore_globs):
                continue

            current["files"].append(
                FileChange(
                    path=file_path,
                    additions=additions,
                    deletions=deletions,
                )
            )
    finally:
        if proc.poll() is None:
            _terminate_process(proc)

    stderr = sanitize(proc.stderr.read() or "")
    if proc.returncode not in (0, None) and not truncated:
        raise ArchaeologyError(stderr or "git failed")

    if not truncated and current and current["files"]:
        commits.append(Commit(**current))

    return commits, truncated
