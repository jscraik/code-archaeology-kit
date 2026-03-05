from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import ArchaeologyError, _notice, DEFAULT_IGNORE_GLOBS
from .git import run_git, parse_git_log
from .metrics import (
    abandoned_structures,
    temporal_coupling,
    era_segmentation,
    compute_base_metrics,
    build_dig_plan,
    rerank_top_actions,
)
from .reporters import render_report, render_share_snippet


SCHEMA_VERSION = "1.2.1"
ADAPTIVE_STRATEGY_VERSION = "v1"
ADAPTIVE_MODES = {"disabled", "shadow", "adaptive"}
_ADAPTIVE_FINGERPRINT_KEYS = (
    "since_days",
    "min_churn_threshold",
    "max_commits",
    "max_files_per_commit",
    "top_actions",
    "large_commit_strategy",
    "use_default_ignores",
    "ignore_rules_applied",
)


def _settings_fingerprint(settings: dict[str, Any]) -> str:
    payload = {key: settings.get(key) for key in _ADAPTIVE_FINGERPRINT_KEYS}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _repo_name_matches(baseline_repo: Any, current_repo_path: Path) -> bool:
    if not isinstance(baseline_repo, str) or not baseline_repo.strip():
        return False
    try:
        baseline_name = Path(baseline_repo).name
    except Exception:
        baseline_name = baseline_repo.split("/")[-1]
    return baseline_name == current_repo_path.name


def _load_baseline_actions(
    baseline_path: Path | None,
    current_repo_path: Path,
    settings_fingerprint: str,
    schema_version: str,
    current_settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state: dict[str, Any] = {
        "baseline_available": False,
        "baseline_source": None,
        "baseline_reason": "baseline_not_requested",
        "baseline_schema_version": None,
        "baseline_head_commit": None,
    }
    if baseline_path is None:
        return [], state

    resolved = baseline_path.expanduser().resolve()
    state["baseline_source"] = str(resolved)

    if not resolved.exists():
        state["baseline_reason"] = "baseline_not_found"
        return [], state
    if resolved.is_dir():
        state["baseline_reason"] = "baseline_path_is_directory"
        return [], state

    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError:
        state["baseline_reason"] = "baseline_unreadable"
        return [], state

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        state["baseline_reason"] = "baseline_invalid_json"
        return [], state
    if not isinstance(payload, dict):
        state["baseline_reason"] = "baseline_invalid_shape"
        return [], state

    baseline_schema_version = payload.get("schema_version")
    state["baseline_schema_version"] = baseline_schema_version if isinstance(baseline_schema_version, str) else None
    current_major = schema_version.split(".", 1)[0]
    baseline_major = state["baseline_schema_version"].split(".", 1)[0] if state["baseline_schema_version"] else None
    if baseline_major != current_major:
        state["baseline_reason"] = "baseline_schema_major_mismatch"
        return [], state

    errors = payload.get("errors")
    if isinstance(errors, list) and len(errors) > 0:
        state["baseline_reason"] = "baseline_contains_errors"
        return [], state

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        state["baseline_reason"] = "baseline_missing_summary"
        return [], state
    repo_path = summary.get("repo_path")
    if not _repo_name_matches(repo_path, current_repo_path):
        state["baseline_reason"] = "baseline_repo_mismatch"
        return [], state
    state["baseline_head_commit"] = summary.get("head_commit") if isinstance(summary.get("head_commit"), str) else None

    baseline_run_meta = payload.get("run_metadata")
    if not isinstance(baseline_run_meta, dict):
        state["baseline_reason"] = "baseline_missing_run_metadata"
        return [], state

    baseline_adaptive = baseline_run_meta.get("adaptive_precision")
    baseline_fp: str | None = None
    if isinstance(baseline_adaptive, dict):
        candidate = baseline_adaptive.get("settings_fingerprint")
        if isinstance(candidate, str):
            baseline_fp = candidate

    if baseline_fp is not None:
        if baseline_fp != settings_fingerprint:
            state["baseline_reason"] = "baseline_settings_fingerprint_mismatch"
            return [], state
    else:
        baseline_settings = payload.get("settings")
        if not isinstance(baseline_settings, dict):
            state["baseline_reason"] = "baseline_missing_settings"
            return [], state
        for key in _ADAPTIVE_FINGERPRINT_KEYS:
            if key == "ignore_rules_applied":
                continue
            if key == "since_days":
                expected = summary.get("since_days")
            else:
                expected = baseline_settings.get(key)
            current = current_settings.get(key)
            if current != expected:
                state["baseline_reason"] = f"baseline_settings_mismatch_{key}"
                return [], state

    actionability = payload.get("actionability")
    if not isinstance(actionability, dict):
        state["baseline_reason"] = "baseline_missing_actionability"
        return [], state
    baseline_actions = actionability.get("top_actions")
    if not isinstance(baseline_actions, list):
        state["baseline_reason"] = "baseline_missing_top_actions"
        return [], state

    state["baseline_available"] = True
    state["baseline_reason"] = "baseline_loaded"
    filtered = [row for row in baseline_actions if isinstance(row, dict)]
    return filtered, state


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
    adaptive_mode: str = "disabled",
    adaptive_baseline_artifact: Path | None = None,
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
    if adaptive_mode not in ADAPTIVE_MODES:
        raise ArchaeologyError("--adaptive-mode must be one of: disabled, shadow, adaptive")

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

    settings: dict[str, Any] = {
        "since_days": since_days,
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
        "adaptive_mode": adaptive_mode,
        "adaptive_baseline_artifact": str(adaptive_baseline_artifact.expanduser().resolve()) if adaptive_baseline_artifact else None,
        "ignore_rules_applied": sorted(set(merged_ignore_globs)),
    }
    settings_fingerprint = _settings_fingerprint(settings)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "repo_path": str(repo_path) if include_repo_path else repo_path.name,
            "head_commit": head,
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "since_days": since_days,
            "total_commits": len(commits),
        },
        "settings": {
            "min_churn_threshold": settings["min_churn_threshold"],
            "include_authors": settings["include_authors"],
            "include_repo_path": settings["include_repo_path"],
            "include_commit_messages": settings["include_commit_messages"],
            "max_commits": settings["max_commits"],
            "max_files_per_commit": settings["max_files_per_commit"],
            "timeout_seconds": settings["timeout_seconds"],
            "top_actions": settings["top_actions"],
            "use_default_ignores": settings["use_default_ignores"],
            "large_commit_strategy": settings["large_commit_strategy"],
            "adaptive_mode": settings["adaptive_mode"],
            "adaptive_baseline_artifact": settings["adaptive_baseline_artifact"],
        },
        "notices": notices,
        "run_metadata": {
            "tool": "cak scan",
            "tool_version": version,
            "schema_path": "config/schemas/archaeology.schema.json",
            "truncated": truncated,
            "runtime_ms": 0,
            "ignore_rules_applied": sorted(set(merged_ignore_globs)),
            "adaptive_precision": {
                "mode": "disabled",
                "strategy_version": ADAPTIVE_STRATEGY_VERSION,
                "baseline_available": False,
                "baseline_source": str(adaptive_baseline_artifact.expanduser().resolve()) if adaptive_baseline_artifact else None,
                "baseline_reason": "adaptive_disabled",
                "settings_fingerprint": settings_fingerprint,
                "baseline_schema_version": None,
                "baseline_head_commit": None,
            },
        },
        "detectors": {
            "abandoned_structures": abandoned_structures(commits, min_churn_threshold),
            "temporal_coupling": temporal,
            "era_segmentation": era_segmentation(commits),
        },
        "base_metrics": compute_base_metrics(commits, include_authors, include_commit_messages),
        "dig_plan": [],
        "actionability": {"top_actions": [], "shadow_top_actions": [], "adaptive_changes": []},
        "errors": [],
    }

    raw_plan = build_dig_plan(payload, top_actions=max(top_actions, 10))
    raw_top_actions = raw_plan[:top_actions]
    payload["dig_plan"] = raw_plan
    payload["actionability"]["top_actions"] = raw_top_actions

    if adaptive_mode != "disabled":
        baseline_actions, baseline_state = _load_baseline_actions(
            baseline_path=adaptive_baseline_artifact,
            current_repo_path=repo_path,
            settings_fingerprint=settings_fingerprint,
            schema_version=SCHEMA_VERSION,
            current_settings=settings,
        )
        adaptive_meta = payload["run_metadata"]["adaptive_precision"]
        adaptive_meta["baseline_available"] = baseline_state["baseline_available"]
        adaptive_meta["baseline_reason"] = baseline_state["baseline_reason"]
        adaptive_meta["baseline_source"] = baseline_state["baseline_source"]
        adaptive_meta["baseline_schema_version"] = baseline_state["baseline_schema_version"]
        adaptive_meta["baseline_head_commit"] = baseline_state["baseline_head_commit"]

        if not baseline_state["baseline_available"]:
            adaptive_meta["mode"] = "learn"
            notices.append(
                _notice(
                    "ADAPTIVE_BASELINE_FALLBACK",
                    f"Adaptive baseline unavailable ({baseline_state['baseline_reason']}); using learn mode.",
                )
            )
        else:
            annotate_reasons = adaptive_mode == "adaptive"
            ranked_top, adaptive_changes = rerank_top_actions(
                raw_actions=raw_plan,
                baseline_actions=baseline_actions,
                top_actions=top_actions,
                annotate_reasons=annotate_reasons,
            )
            payload["actionability"]["adaptive_changes"] = adaptive_changes

            if adaptive_mode == "shadow":
                adaptive_meta["mode"] = "shadow"
                payload["actionability"]["shadow_top_actions"] = ranked_top
                notices.append(
                    _notice(
                        "ADAPTIVE_SHADOW_MODE",
                        "Adaptive shadow mode active; top_actions kept raw and shadow_top_actions contains adaptive ranking.",
                    )
                )
            else:
                adaptive_meta["mode"] = "adaptive"
                payload["actionability"]["top_actions"] = ranked_top
                notices.append(
                    _notice(
                        "ADAPTIVE_MODE_ACTIVE",
                        "Adaptive mode active; top_actions were re-ranked against the baseline profile.",
                    )
                )

    payload["run_metadata"]["adaptive_precision"]["settings_fingerprint"] = settings_fingerprint
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
