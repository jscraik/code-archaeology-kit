from __future__ import annotations
import subprocess
import time
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from .models import Commit, FileChange

from .utils import ArchaeologyError, sanitize, normalize_path, matches_any


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

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
        "--pretty=format:%H|%ai|%an|%ae|%s",
        "--numstat",
    ]

    commits: list[Commit] = []
    current: dict[str, Any] | None = None
    truncated = False

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

            if "|" in line and not line.startswith("\t"):
                if current and current["files"]:
                    commits.append(Commit(**current))
                    if len(commits) >= max_commits:
                        truncated = True
                        _terminate_process(proc)
                        break

                parts = line.split("|", 4)
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
                if parsed_date is not None:
                    current["date_obj"] = parsed_date
                continue

            if current is None:
                continue

            m = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if not m:
                continue

            file_path = sanitize(normalize_path(m.group(3)), 800)
            if matches_any(file_path, ignore_globs):
                continue

            current["files"].append(
                FileChange(
                    path=file_path,
                    additions=0 if m.group(1) == "-" else int(m.group(1)),
                    deletions=0 if m.group(2) == "-" else int(m.group(2)),
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
