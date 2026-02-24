from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import ArchaeologyError, _notice, DEFAULT_IGNORE_GLOBS
from .git import run_git, parse_git_log
from .metrics import abandoned_structures, temporal_coupling, era_segmentation, compute_base_metrics, build_dig_plan
from .reporters import render_report, render_share_snippet



def write_share_snippet(payload: dict[str, Any], output_dir: Path, force: bool) -> Path:
    output = output_dir.expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchaeologyError(f"Failed to prepare output directory: {output}") from exc

    share_path = output / "archaeology_share.md"
    if share_path.exists() and share_path.is_dir():
        raise ArchaeologyError(f"Output path is a directory: {share_path}")
    if share_path.exists() and not force:
        raise ArchaeologyError(f"Refusing overwrite: {share_path} (use --force)")

    content = render_share_snippet(payload)

    tmp_path = share_path.with_name(f"{share_path.name}.tmp.{os.getpid()}")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        tmp_path.replace(share_path)
    except OSError as exc:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise ArchaeologyError(f"Failed to write file: {share_path}") from exc

    return share_path

def _validate_payload_schema(payload: dict[str, Any], schema_path: Path) -> None:
    try:
        import jsonschema
    except ImportError:
        return

    schema = json.loads(schema_path.read_text())
    jsonschema.validate(payload, schema)

def analyze_repo(
    repo: Path,
    since_days: int,
    min_churn_threshold: int,
    include_authors: bool,
    include_repo_path: bool,
    include_commit_messages: bool,
    timeout_seconds: int,
    max_commits: int,
    max_files_per_commit: int,
    version: str,
    ignore_globs: list[str] | None = None,
    use_default_ignores: bool = True,
    top_actions: int = 3,
    large_commit_strategy: str = "cap",
) -> dict[str, Any]:
    if since_days < 1:
        raise ArchaeologyError("--since-days must be >= 1")
    if min_churn_threshold < 1:
        raise ArchaeologyError("--min-churn-threshold must be >= 1")
    if timeout_seconds < 1:
        raise ArchaeologyError("--timeout-seconds must be >= 1")
    if max_commits < 1:
        raise ArchaeologyError("--max-commits must be >= 1")
    if max_files_per_commit < 2:
        raise ArchaeologyError("--max-files-per-commit must be >= 2")
    if top_actions < 1:
        raise ArchaeologyError("--top-actions must be >= 1")
    if large_commit_strategy not in {"cap", "skip"}:
        raise ArchaeologyError("--large-commit-strategy must be one of: cap, skip")

    repo_path = repo.expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir() or not (repo_path / ".git").exists():
        raise ArchaeologyError(f"Not a git repo: {repo}")

    merged_ignore_globs: list[str] = []
    if use_default_ignores:
        merged_ignore_globs.extend(DEFAULT_IGNORE_GLOBS)
    if ignore_globs:
        merged_ignore_globs.extend(ignore_globs)

    start = time.time()

    try:
        commits, truncated = parse_git_log(
            repo=repo_path,
            since_days=since_days,
            timeout_seconds=timeout_seconds,
            max_commits=max_commits,
            ignore_globs=merged_ignore_globs,
        )
    except ArchaeologyError as exc:
        message = str(exc)
        if "does not have any commits yet" in message or "ambiguous argument 'HEAD'" in message:
            raise ArchaeologyError("Repository has no commits to analyze") from exc
        raise
    try:
        head = run_git(["git", "-C", str(repo_path), "rev-parse", "HEAD"], timeout_seconds).strip()
    except ArchaeologyError as exc:
        message = str(exc)
        if "does not have any commits yet" in message or "ambiguous argument 'HEAD'" in message:
            raise ArchaeologyError("Repository has no commits to analyze") from exc
        raise

    temporal = temporal_coupling(repo_path, commits, max(2, min_churn_threshold), max_files_per_commit, large_commit_strategy)

    notices: list[dict[str, str]] = []
    if truncated:
        notices.append(
            _notice(
                "TRUNCATED_COMMITS",
                f"Commit parsing stopped at max_commits={max_commits}; results may be incomplete.",
            )
        )
    if not include_repo_path:
        notices.append(
            _notice(
                "REPO_PATH_REDACTED",
                "summary.repo_path is redacted to basename by default (use --include-repo-path to include full path).",
            )
        )
    if not include_commit_messages:
        notices.append(
            _notice(
                "COMMIT_MESSAGES_REDACTED",
                "Commit messages are redacted by default (use --include-commit-messages to include sanitized messages).",
            )
        )
    if large_commit_strategy == "cap" and temporal.get("capped_large_commits", 0) > 0:
        notices.append(
            _notice(
                "TEMPORAL_COUPLING_CAPPED",
                f"Temporal coupling capped {temporal['capped_large_commits']} commit(s) to max_files_per_commit={max_files_per_commit}.",
            )
        )
    if large_commit_strategy == "skip" and temporal.get("skipped_large_commits", 0) > 0:
        notices.append(
            _notice(
                "TEMPORAL_COUPLING_SKIPPED",
                f"Temporal coupling skipped {temporal['skipped_large_commits']} commit(s) with > max_files_per_commit={max_files_per_commit}.",
            )
        )

    payload: dict[str, Any] = {
        "schema_version": "1.2.0",
        "summary": {
            "repo_path": str(repo_path) if include_repo_path else repo_path.name,
            "head_commit": head,
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "since_days": since_days,
            "total_commits": len(commits),
        },
        "settings": {
            "min_churn_threshold": min_churn_threshold,
            "include_authors": include_authors,
            "include_repo_path": include_repo_path,
            "include_commit_messages": include_commit_messages,
            "max_commits": max_commits,
            "max_files_per_commit": max_files_per_commit,
            "timeout_seconds": timeout_seconds,
            "top_actions": top_actions,
            "use_default_ignores": use_default_ignores,
            "large_commit_strategy": large_commit_strategy,
        },
        "notices": notices,
        "run_metadata": {
            "tool": "cak scan",
            "tool_version": version,
            "schema_path": "config/schemas/archaeology.schema.json",
            "truncated": truncated,
            "runtime_ms": 0,
            "ignore_rules_applied": sorted(set(merged_ignore_globs)),
        },
        "detectors": {
            "abandoned_structures": abandoned_structures(commits, min_churn_threshold),
            "temporal_coupling": temporal,
            "era_segmentation": era_segmentation(commits),
        },
        "base_metrics": compute_base_metrics(commits, include_authors, include_commit_messages),
        "dig_plan": [],
        "actionability": {"top_actions": []},
        "errors": [],
    }

    payload["dig_plan"] = build_dig_plan(payload, top_actions=max(top_actions, 10))
    payload["actionability"]["top_actions"] = build_dig_plan(payload, top_actions=top_actions)
    payload["run_metadata"]["runtime_ms"] = int((time.time() - start) * 1000)

    try:
        _validate_payload_schema(payload, Path(__file__).resolve().parents[2] / "config" / "schemas" / "archaeology.schema.json")
    except Exception as exc:
        raise ArchaeologyError(f"Schema validation failed: {exc}") from exc

    return payload

def write_payload(payload: dict[str, Any], output_dir: Path, fmt: str, force: bool) -> tuple[Path | None, Path | None]:
    if fmt not in {"json", "md", "both"}:
        raise ArchaeologyError("--format must be one of: json, md, both")

    output = output_dir.expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchaeologyError(f"Failed to prepare output directory: {output}") from exc

    json_path = output / "archaeology.json"
    md_path = output / "archaeology_report.md"

    def write_temp(path: Path, content: str) -> Path:
        tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        except OSError as exc:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise ArchaeologyError(f"Failed to write file: {path}") from exc
        return tmp_path

    json_content: str | None = None
    md_content: str | None = None

    if fmt in {"json", "both"}:
        if json_path.exists() and json_path.is_dir():
            raise ArchaeologyError(f"Output path is a directory: {json_path}")
        if json_path.exists() and not force:
            raise ArchaeologyError(f"Refusing overwrite: {json_path} (use --force)")
        json_content = json.dumps(payload, indent=2)
    else:
        json_path = None

    if fmt in {"md", "both"}:
        if md_path.exists() and md_path.is_dir():
            raise ArchaeologyError(f"Output path is a directory: {md_path}")
        if md_path.exists() and not force:
            raise ArchaeologyError(f"Refusing overwrite: {md_path} (use --force)")
        md_content = render_report(payload)
    else:
        md_path = None

    # Write temps first, then replace, to reduce partial-final state when fmt="both".
    pending: list[tuple[Path, str]] = []
    if json_path is not None and json_content is not None:
        pending.append((json_path, json_content))
    if md_path is not None and md_content is not None:
        pending.append((md_path, md_content))

    temp_files: list[tuple[Path, Path]] = []
    try:
        for final_path, content in pending:
            temp_path = write_temp(final_path, content)
            temp_files.append((temp_path, final_path))
    except ArchaeologyError:
        for temp_path, _ in temp_files:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
        raise

    backups: list[tuple[Path, Path]] = []
    replaced_finals: list[Path] = []
    try:
        for _, final_path in temp_files:
            if final_path.exists():
                backup_path = final_path.with_name(f"{final_path.name}.bak.{os.getpid()}")
                final_path.replace(backup_path)
                backups.append((final_path, backup_path))

        for temp_path, final_path in temp_files:
            temp_path.replace(final_path)
            replaced_finals.append(final_path)
    except OSError as exc:
        for stale_temp, _ in temp_files:
            try:
                if stale_temp.exists():
                    stale_temp.unlink()
            except OSError:
                pass
        for final_path in replaced_finals:
            try:
                if final_path.exists():
                    final_path.unlink()
            except OSError:
                pass
        for final_path, backup_path in reversed(backups):
            try:
                if backup_path.exists():
                    backup_path.replace(final_path)
            except OSError:
                pass
        raise ArchaeologyError(f"Failed to write file: {final_path}") from exc
    finally:
        for _, backup_path in backups:
            try:
                if backup_path.exists():
                    backup_path.unlink()
            except OSError:
                pass

    return json_path, md_path
