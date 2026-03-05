from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .models import Commit

from .utils import classify_path, confidence, matches_any, LOW_VALUE_ABANDONED_GLOBS
from .ast_coupling import check_logical_coupling


_PRIORITY_SCORE = {"high": 2, "medium": 1, "low": 0}
_LEVERAGE_SCORE = {"high": 2, "medium": 1, "low": 0}
_EFFORT_SCORE = {"low": 2, "medium": 1, "high": 0}


def _action_key(action: dict[str, Any]) -> str:
    return f"{action.get('action', '')}::{action.get('target', '')}"


def rerank_top_actions(
    raw_actions: list[dict[str, Any]],
    baseline_actions: list[dict[str, Any]],
    top_actions: int,
    annotate_reasons: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if top_actions < 1:
        raise ValueError("top_actions must be >= 1")

    if not raw_actions:
        return [], []

    baseline_index = {_action_key(action): idx + 1 for idx, action in enumerate(baseline_actions)}

    scored: list[tuple[tuple[Any, ...], int, dict[str, Any], str]] = []
    for source_index, action in enumerate(raw_actions):
        copied = dict(action)
        key = _action_key(copied)
        baseline_rank = baseline_index.get(key)
        unseen = baseline_rank is None
        reason = "not_seen_in_baseline" if unseen else f"seen_in_baseline_rank_{baseline_rank}"

        priority_score = _PRIORITY_SCORE.get(str(copied.get("priority", "medium")), 0)
        leverage_score = _LEVERAGE_SCORE.get(str(copied.get("expected_leverage", "medium")), 0)
        effort_score = _EFFORT_SCORE.get(str(copied.get("effort", "medium")), 1)

        sort_key = (
            0 if unseen else 1,  # unseen first
            -priority_score,
            -leverage_score,
            -effort_score,
            baseline_rank or 10_000,
            source_index,
            str(copied.get("target", "")),
        )
        scored.append((sort_key, source_index, copied, reason))

    scored.sort(key=lambda row: row[0])
    ranked_all = [entry[2] for entry in scored]
    reasons_by_key = {_action_key(entry[2]): entry[3] for entry in scored}
    ranked_top = ranked_all[:top_actions]
    raw_top = raw_actions[:top_actions]

    raw_top_pos = {_action_key(action): idx + 1 for idx, action in enumerate(raw_top)}
    ranked_top_pos = {_action_key(action): idx + 1 for idx, action in enumerate(ranked_top)}

    changes: list[dict[str, Any]] = []
    all_keys = sorted(set(raw_top_pos) | set(ranked_top_pos))
    for key in all_keys:
        original_position = raw_top_pos.get(key)
        new_position = ranked_top_pos.get(key)
        if original_position == new_position:
            continue

        representative = None
        for action in ranked_top:
            if _action_key(action) == key:
                representative = action
                break
        if representative is None:
            for action in raw_top:
                if _action_key(action) == key:
                    representative = action
                    break
        if representative is None:
            continue

        reason = reasons_by_key.get(key, "reordered_by_adaptive_baseline")
        changes.append(
            {
                "action": representative.get("action", ""),
                "target": representative.get("target", ""),
                "original_position": original_position,
                "new_position": new_position,
                "reason": reason,
            }
        )

    if annotate_reasons:
        annotated: list[dict[str, Any]] = []
        for action in ranked_top:
            copied = dict(action)
            key = _action_key(copied)
            reason = reasons_by_key.get(key)
            if reason:
                existing = str(copied.get("rationale", "") or "").strip()
                suffix = f"adaptive_reason={reason}"
                copied["rationale"] = f"{existing} | {suffix}".strip(" |")
            annotated.append(copied)
        ranked_top = annotated

    return ranked_top, changes


def abandoned_structures(
    commits: list[Commit],
    min_churn: int,
    stale_days: int = 90,
) -> list[dict[str, Any]]:
    if min_churn < 1:
        raise ValueError("min_churn must be >= 1")
    if stale_days < 0:
        raise ValueError("stale_days must be >= 0")

    now = datetime.now(timezone.utc)
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"commits": 0, "recent": 0, "last": None, "authors": set()}
    )

    for commit in commits:
        date_obj = commit.date_obj
        if date_obj is None:
            continue
        is_recent = (now - date_obj).days <= stale_days

        for file_change in commit.files:
            path = file_change.path
            entry = stats[path]
            entry["commits"] += 1
            entry["authors"].add(commit.author_email)
            entry["last"] = date_obj if entry["last"] is None or date_obj > entry["last"] else entry["last"]
            if is_recent:
                entry["recent"] += 1

    out: list[dict[str, Any]] = []
    for path, entry in stats.items():
        if entry["commits"] < min_churn or entry["recent"] > 0 or entry["last"] is None:
            continue

        stale = (now - entry["last"]).days
        if stale < stale_days:
            continue

        path_class = classify_path(path)
        low_value_penalty = 0.2 if matches_any(path, LOW_VALUE_ABANDONED_GLOBS) else 0.0
        raw_score = (entry["commits"] / max(min_churn, 1)) * 0.3 + (stale / 365.0) * 0.7
        score = max(0.0, min(1.0, raw_score - low_value_penalty))

        out.append(
            {
                "file": path,
                "path_class": path_class,
                "historical_commits": entry["commits"],
                "recent_commits": entry["recent"],
                "days_since_last_change": stale,
                "authors": len(entry["authors"]),
                "confidence": confidence(score),
                "confidence_explainer": (
                    f"churn={entry['commits']}, stale_days={stale}, class={path_class}, penalty={low_value_penalty}"
                ),
            }
        )

    out.sort(
        key=lambda row: (
            row["path_class"] in {"docs", "generated"},
            -row["days_since_last_change"],
            -row["historical_commits"],
            row["file"],
        )
    )
    return out[:50]

def classify_coupling(file_a: str, file_b: str, ratio: float, count: int) -> str:
    class_a = classify_path(file_a)
    class_b = classify_path(file_b)
    pair = {class_a, class_b}

    if pair <= {"test", "docs", "generated"}:
        return "expected"
    if "generated" in pair and "product" in pair:
        return "risky"
    if "product" in pair and "infra" in pair:
        return "risky"
    if ratio >= 0.7 and count >= 4 and class_a != class_b:
        return "suspicious"
    return "expected" if class_a == class_b else "risky"

def temporal_coupling(
    repo_path: Path,
    commits: list[Commit],
    min_co_changes: int,
    max_files_per_commit: int,
    large_commit_strategy: str,
) -> dict[str, Any]:
    if min_co_changes < 1:
        raise ValueError("min_co_changes must be >= 1")
    if max_files_per_commit < 2:
        raise ValueError("max_files_per_commit must be >= 2")
    if large_commit_strategy not in {"cap", "skip"}:
        raise ValueError("large_commit_strategy must be one of: cap, skip")

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    file_counts: dict[str, int] = defaultdict(int)
    imports_cache: dict[str, set[str]] = {}
    skipped = 0
    capped = 0

    for commit in commits:
        files = sorted({f.path for f in commit.files})

        if len(files) > max_files_per_commit:
            if large_commit_strategy == "skip":
                skipped += 1
                continue
            capped += 1
            files = files[:max_files_per_commit]

        for file_path in files:
            file_counts[file_path] += 1

        if len(files) < 2:
            continue

        for idx, left in enumerate(files):
            for right in files[idx + 1 :]:
                pair_counts[(left, right)] += 1

    pairs = []
    for (left, right), count in pair_counts.items():
        if count < min_co_changes:
            continue

        denom = min(file_counts[left], file_counts[right])
        ratio = round((count / denom), 4) if denom else 0.0
        coupling_class = classify_coupling(left, right, ratio, count)

        risk_bonus = 0.15 if coupling_class in {"risky", "suspicious"} else 0.0
        is_logically_coupled = False
        if coupling_class in {"risky", "suspicious"}:
            is_logically_coupled = check_logical_coupling(repo_path, left, right, imports_cache=imports_cache)
            if is_logically_coupled:
                risk_bonus = 0.35
                coupling_class = "suspicious" # elevate to suspicious if logically coupled

        score = max(0.0, min(1.0, ratio * 0.65 + min(1.0, count / 10.0) * 0.35 + risk_bonus))

        pairs.append(
            {
                "file_a": left,
                "file_b": right,
                "class_a": classify_path(left),
                "class_b": classify_path(right),
                "co_change_commits": count,
                "coupling_ratio": ratio,
                "coupling_class": coupling_class,
                "is_logically_coupled": is_logically_coupled,
                "confidence": confidence(score),
                "confidence_explainer": f"ratio={ratio}, co_changes={count}, coupling_class={coupling_class}, logically_coupled={is_logically_coupled}",
            }
        )

    pairs.sort(
        key=lambda row: (
            row["coupling_class"] == "expected",
            -row["co_change_commits"],
            -row["coupling_ratio"],
            row["file_a"],
            row["file_b"],
        )
    )

    return {
        "pairs": pairs[:50],
        "skipped_large_commits": skipped,
        "capped_large_commits": capped,
        "max_files_per_commit": max_files_per_commit,
    }

def era_segmentation(commits: list[Commit]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for commit in commits:
        date_obj = commit.date_obj
        if date_obj is None:
            continue
        buckets[date_obj.strftime("%Y-%m")].append(commit)

    out = []
    for month in sorted(buckets):
        month_commits = buckets[month]
        growth = 0
        churn: dict[str, int] = defaultdict(int)

        for commit in month_commits:
            for file_change in commit.files:
                growth += file_change.additions - file_change.deletions
                churn[file_change.path] += 1

        top_file = max(churn.items(), key=lambda item: item[1])[0] if churn else None
        max_churn = max(churn.values()) if churn else 0

        if growth > 200:
            label = "expansion"
        elif max_churn >= 8:
            label = "stabilization"
        else:
            label = "maintenance"

        out.append(
            {
                "era": month,
                "label": label,
                "commits": len(month_commits),
                "growth_signal": growth,
                "top_churn_file": top_file,
            }
        )

    return out

def compute_base_metrics(commits: list[Commit], include_authors: bool, include_commit_messages: bool) -> dict[str, Any]:
    file_churn = defaultdict(int)
    file_growth = defaultdict(int)
    commit_themes: dict[str, int] = defaultdict(int)
    language_breakdown: dict[str, int] = defaultdict(int)

    author_counts: dict[str, int] = defaultdict(int)

    for commit in commits:
        message = commit.message.lower()
        if message.startswith("feat"):
            commit_themes["feat"] += 1
        elif message.startswith("fix"):
            commit_themes["fix"] += 1
        elif "refactor" in message:
            commit_themes["refactor"] += 1
        else:
            commit_themes["other"] += 1

        if include_authors:
            author_counts[f"{commit.author_name} <{commit.author_email}>"] += 1

        seen_langs: set[str] = set()
        for file_change in commit.files:
            path = file_change.path
            file_churn[path] += 1
            file_growth[path] += file_change.additions - file_change.deletions

            suffix = Path(path).suffix.lower()
            language = {
                ".py": "Python",
                ".ts": "TypeScript",
                ".tsx": "TypeScript",
                ".mts": "TypeScript",
                ".cts": "TypeScript",
                ".js": "JavaScript",
                ".jsx": "JavaScript",
                ".mjs": "JavaScript",
                ".cjs": "JavaScript",
                ".java": "Java",
                ".kt": "Kotlin",
                ".go": "Go",
                ".rb": "Ruby",
                ".cs": "C#",
                ".cpp": "C++",
                ".c": "C",
                ".rs": "Rust",
            }.get(suffix, "Other")
            seen_langs.add(language)

        for language in seen_langs:
            language_breakdown[language] += 1

    metrics: dict[str, Any] = {
        "file_churn": [
            {"file": path, "commits": count}
            for path, count in sorted(file_churn.items(), key=lambda item: (-item[1], item[0]))[:50]
        ],
        "file_growth": [
            {"file": path, "net_lines": net}
            for path, net in sorted(file_growth.items(), key=lambda item: (-item[1], item[0]))[:50]
        ],
        "commit_themes": dict(sorted(commit_themes.items(), key=lambda item: (-item[1], item[0]))),
        "recent_refactors": [
            {
                "commit": commit.hash,
                "date": commit.date,
                "message": commit.message if include_commit_messages else "<redacted>",
                "message_redacted": not include_commit_messages,
            }
            for commit in commits
            if "refactor" in commit.message.lower()
        ][:20],
        "time_buckets": era_segmentation(commits),
        "language_breakdown": [
            {"language": lang, "commits": count}
            for lang, count in sorted(language_breakdown.items(), key=lambda item: (-item[1], item[0]))
        ],
    }

    if include_authors:
        metrics["author_activity"] = [
            {"author": author, "commits": count}
            for author, count in sorted(author_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ]

    return metrics

def build_dig_plan(payload: dict[str, Any], top_actions: int) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    source_limit = max(top_actions, 5)

    for item in payload["detectors"]["abandoned_structures"][:source_limit]:
        leverage = "high" if item["path_class"] == "product" else "medium"
        effort = "medium" if item["historical_commits"] >= 10 else "low"
        actions.append(
            {
                "priority": "high" if item["confidence"] == "high" else "medium",
                "action": "audit_abandoned_file",
                "target": item["file"],
                "effort": effort,
                "expected_leverage": leverage,
                "rationale": (
                    f"{item['historical_commits']} historical commits; "
                    f"stale {item['days_since_last_change']}d; class={item['path_class']}"
                ),
            }
        )

    for pair in payload["detectors"]["temporal_coupling"]["pairs"][:source_limit]:
        leverage = "high" if pair["coupling_class"] in {"risky", "suspicious"} else "medium"
        actions.append(
            {
                "priority": "high" if pair["coupling_class"] in {"risky", "suspicious"} else "medium",
                "action": "review_temporal_coupling",
                "target": f"{pair['file_a']} <-> {pair['file_b']}",
                "effort": "medium",
                "expected_leverage": leverage,
                "rationale": (
                    f"co-change={pair['co_change_commits']}, ratio={pair['coupling_ratio']}, "
                    f"class={pair['coupling_class']}"
                ),
            }
        )

    actions.sort(
        key=lambda item: (
            item["priority"] != "high",
            item["expected_leverage"] != "high",
            item["effort"] == "high",
            item["target"],
        )
    )

    if not actions:
        for row in payload.get("base_metrics", {}).get("file_churn", [])[: max(3, top_actions)]:
            actions.append(
                {
                    "priority": "medium",
                    "action": "review_high_churn_file",
                    "target": row["file"],
                    "effort": "low",
                    "expected_leverage": "medium",
                    "rationale": f"fallback action from churn ranking ({row['commits']} commits in window)",
                }
            )

    return actions[:top_actions]
