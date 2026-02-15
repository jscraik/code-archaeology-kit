from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DEFAULT_IGNORE_GLOBS = [
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    "node_modules/**",
    "dist/**",
    "build/**",
    "target/**",
    ".venv/**",
    "venv/**",
    "coverage/**",
    "*.lock",
]

LOW_VALUE_ABANDONED_GLOBS = [
    ".github/**",
    "docs/**",
    "**/ISSUE_TEMPLATE/**",
    "**/*.md",
]


class ArchaeologyError(Exception):
    """Raised for CLI contract and runtime failures."""

def _terminate_process(proc: subprocess.Popen[str]) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _notice(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def sanitize(value: str, max_len: int = 400) -> str:
    cleaned = CONTROL_CHARS_RE.sub("", value).replace("\r", " ").replace("\n", " ").strip()
    return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def classify_path(path: str) -> str:
    p = normalize_path(path).lower()
    name = p.split("/")[-1]

    if "__pycache__" in p or name.endswith(".pyc"):
        return "generated"
    if any(token in p for token in ["/test/", "/tests/", "test_", "/fixtures/", "/__tests__/"]):
        return "test"
    if p.startswith(".github/") or any(token in p for token in ["/infra/", "/ops/", "docker", "k8s", "terraform", ".yml", ".yaml"]):
        return "infra"
    if p.startswith("docs/") or name.endswith(".md"):
        return "docs"
    if any(token in p for token in ["dist/", "build/", "target/", "node_modules/"]):
        return "generated"
    if any(token in p for token in ["src/", "lib/", "app/"]):
        return "product"
    return "unknown"


def confidence(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


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
) -> tuple[list[dict[str, Any]], bool]:
    since_date = (datetime.now(UTC) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    cmd = [
        "git",
        "-C",
        str(repo),
        "log",
        f"--since={since_date}",
        "--pretty=format:%H|%ai|%an|%ae|%s",
        "--numstat",
    ]

    commits: list[dict[str, Any]] = []
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
                    commits.append(current)
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
                {
                    "path": file_path,
                    "additions": 0 if m.group(1) == "-" else int(m.group(1)),
                    "deletions": 0 if m.group(2) == "-" else int(m.group(2)),
                }
            )
    finally:
        if proc.poll() is None:
            _terminate_process(proc)

    stderr = sanitize(proc.stderr.read() or "")
    if proc.returncode not in (0, None) and not truncated:
        raise ArchaeologyError(stderr or "git failed")

    if not truncated and current and current["files"]:
        commits.append(current)

    return commits, truncated


def abandoned_structures(
    commits: list[dict[str, Any]],
    min_churn: int,
    stale_days: int = 90,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"commits": 0, "recent": 0, "last": None, "authors": set()}
    )

    for commit in commits:
        date_obj = commit.get("date_obj")
        if date_obj is None:
            continue
        is_recent = (now - date_obj).days <= stale_days

        for file_change in commit["files"]:
            path = file_change["path"]
            entry = stats[path]
            entry["commits"] += 1
            entry["authors"].add(commit["author_email"])
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
    commits: list[dict[str, Any]],
    min_co_changes: int,
    max_files_per_commit: int,
    large_commit_strategy: str,
) -> dict[str, Any]:
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    file_counts: dict[str, int] = defaultdict(int)
    skipped = 0
    capped = 0

    for commit in commits:
        files = sorted({f["path"] for f in commit["files"]})
        if len(files) < 2:
            for file_path in files:
                file_counts[file_path] += 1
            continue

        for file_path in files:
            file_counts[file_path] += 1

        if len(files) > max_files_per_commit:
            if large_commit_strategy == "skip":
                skipped += 1
                continue
            capped += 1
            files = files[:max_files_per_commit]

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
                "confidence": confidence(score),
                "confidence_explainer": f"ratio={ratio}, co_changes={count}, coupling_class={coupling_class}",
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


def era_segmentation(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for commit in commits:
        date_obj = commit.get("date_obj")
        if date_obj is None:
            continue
        buckets[date_obj.strftime("%Y-%m")].append(commit)

    out = []
    for month in sorted(buckets):
        month_commits = buckets[month]
        growth = 0
        churn: dict[str, int] = defaultdict(int)

        for commit in month_commits:
            for file_change in commit["files"]:
                growth += file_change["additions"] - file_change["deletions"]
                churn[file_change["path"]] += 1

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


def compute_base_metrics(commits: list[dict[str, Any]], include_authors: bool, include_commit_messages: bool) -> dict[str, Any]:
    file_churn = defaultdict(int)
    file_growth = defaultdict(int)
    commit_themes: dict[str, int] = defaultdict(int)
    language_breakdown: dict[str, int] = defaultdict(int)

    author_counts: dict[str, int] = defaultdict(int)

    for commit in commits:
        message = commit["message"].lower()
        if message.startswith("feat"):
            commit_themes["feat"] += 1
        elif message.startswith("fix"):
            commit_themes["fix"] += 1
        elif "refactor" in message:
            commit_themes["refactor"] += 1
        else:
            commit_themes["other"] += 1

        if include_authors:
            author_counts[f"{commit['author_name']} <{commit['author_email']}>"] += 1

        seen_langs: set[str] = set()
        for file_change in commit["files"]:
            path = file_change["path"]
            file_churn[path] += 1
            file_growth[path] += file_change["additions"] - file_change["deletions"]

            suffix = Path(path).suffix.lower()
            language = {
                ".py": "Python",
                ".ts": "TypeScript",
                ".tsx": "TypeScript",
                ".js": "JavaScript",
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
                "commit": commit["hash"],
                "date": commit["date"],
                "message": commit["message"] if include_commit_messages else "<redacted>",
                "message_redacted": not include_commit_messages,
            }
            for commit in commits
            if "refactor" in commit["message"].lower()
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

    for item in payload["detectors"]["abandoned_structures"][:5]:
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

    for pair in payload["detectors"]["temporal_coupling"]["pairs"][:5]:
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


def render_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    ignore_rules = payload["run_metadata"]["ignore_rules_applied"]
    top_actions = payload["actionability"]["top_actions"]
    notices = payload.get("notices", [])

    lines = [
        "# Code Archaeology Report",
        "",
        "## Summary",
        f"- Repository: `{summary['repo_path']}`",
        f"- Head commit: `{summary['head_commit']}`",
        f"- Window: last {summary['since_days']} days",
        f"- Total commits: {summary['total_commits']}",
        f"- Generated (UTC): {summary['generated_at_utc']}",
        "",
        "## Notices",
    ]

    if notices:
        for notice in notices:
            lines.append(f"- `{notice.get('code', 'NOTICE')}`: {notice.get('message', '')}")
    else:
        lines.append("- (none)")

    lines.extend([
        "",
        "## Signal Quality",
        "- Ignore rules applied:",
    ])

    for rule in ignore_rules:
        lines.append(f"  - `{rule}`")

    lines.extend(["", "## Top High-Leverage Actions"])
    for action in top_actions:
        lines.append(
            f"- [{action['priority']}] **{action['action']}** `{action['target']}` "
            f"(effort={action['effort']}, leverage={action['expected_leverage']}) — {action['rationale']}"
        )

    lines.extend(["", "## Abandoned structures"])
    for row in payload["detectors"]["abandoned_structures"][:10]:
        lines.append(
            f"- `{row['file']}` ({row['historical_commits']} commits, {row['days_since_last_change']}d stale, "
            f"class={row['path_class']}, confidence={row['confidence']})"
        )

    lines.extend(["", "## Temporal coupling"])
    for row in payload["detectors"]["temporal_coupling"]["pairs"][:10]:
        lines.append(
            f"- `{row['file_a']}` <-> `{row['file_b']}` "
            f"(co-changes={row['co_change_commits']}, ratio={row['coupling_ratio']}, class={row['coupling_class']})"
        )

    lines.extend(["", "## Coupling classes"])
    class_counts: dict[str, int] = defaultdict(int)
    for row in payload["detectors"]["temporal_coupling"]["pairs"]:
        class_counts[row["coupling_class"]] += 1

    for coupling_class in ["suspicious", "risky", "expected"]:
        lines.append(f"- {coupling_class}: {class_counts.get(coupling_class, 0)}")

    lines.extend(["", "## Era segmentation"])
    for row in payload["detectors"]["era_segmentation"]:
        lines.append(f"- {row['era']}: {row['label']} ({row['commits']} commits)")

    if payload["errors"]:
        lines.extend(["", "## Errors"])
        for error in payload["errors"]:
            lines.append(f"- `{error['code']}`: {error['message']}")

    return "\n".join(lines) + "\n"


def render_share_snippet(payload: dict[str, Any]) -> str:
    """Render a short, share-ready Markdown snippet for Slack/PR comments.

    Privacy defaults:
    - Uses payload["summary"]["repo_path"], which is basename-only unless --include-repo-path was set.
    - Does not include commit messages.
    """
    summary = payload["summary"]
    top_actions = payload.get("actionability", {}).get("top_actions", [])[:5]

    pairs = payload.get("detectors", {}).get("temporal_coupling", {}).get("pairs", [])
    coupling_counts: dict[str, int] = defaultdict(int)
    for row in pairs:
        coupling_counts[row.get("coupling_class", "unknown")] += 1

    abandoned = payload.get("detectors", {}).get("abandoned_structures", [])

    lines = [
        "## Code Archaeology Snapshot",
        f"- Repo: `{summary.get('repo_path', '')}`",
        f"- Window: last {summary.get('since_days', '')} days",
        f"- Head: `{str(summary.get('head_commit', ''))[:7]}`",
        "",
        "### Top actions",
    ]

    if top_actions:
        for action in top_actions:
            lines.append(f"- **{action['action']}** `{action['target']}` — {action['rationale']}")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "### Signals (counts)",
            f"- Temporal coupling: suspicious={coupling_counts.get('suspicious', 0)}, risky={coupling_counts.get('risky', 0)}",
            f"- Abandoned structures (top list size): {len(abandoned)}",
            "",
            "### Re-run",
            "```bash",
            f"cak scan --repo /path/to/repo --since-days {summary.get('since_days', 365)} --format both --output-dir ./artifacts",
            "```",
        ]
    )

    return "\n".join(lines) + "\n"


def write_share_snippet(payload: dict[str, Any], output_dir: Path, force: bool) -> Path:
    output = output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    share_path = output / "archaeology_share.md"
    if share_path.exists() and not force:
        raise ArchaeologyError(f"Refusing overwrite: {share_path} (use --force)")

    content = render_share_snippet(payload)

    tmp_path = share_path.with_name(f"{share_path.name}.tmp.{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    tmp_path.replace(share_path)

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

    commits, truncated = parse_git_log(
        repo=repo_path,
        since_days=since_days,
        timeout_seconds=timeout_seconds,
        max_commits=max_commits,
        ignore_globs=merged_ignore_globs,
    )
    head = run_git(["git", "-C", str(repo_path), "rev-parse", "HEAD"], timeout_seconds).strip()

    temporal = temporal_coupling(commits, max(2, min_churn_threshold), max_files_per_commit, large_commit_strategy)

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
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
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

    _validate_payload_schema(payload, Path(__file__).resolve().parents[2] / "config" / "schemas" / "archaeology.schema.json")

    return payload


def write_payload(payload: dict[str, Any], output_dir: Path, fmt: str, force: bool) -> tuple[Path | None, Path | None]:
    output = output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    json_path = output / "archaeology.json"
    md_path = output / "archaeology_report.md"

    def atomic_write(path: Path, content: str) -> None:
        tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        tmp_path.replace(path)

    json_content: str | None = None
    md_content: str | None = None

    if fmt in {"json", "both"}:
        if json_path.exists() and not force:
            raise ArchaeologyError(f"Refusing overwrite: {json_path} (use --force)")
        json_content = json.dumps(payload, indent=2)
    else:
        json_path = None

    if fmt in {"md", "both"}:
        if md_path.exists() and not force:
            raise ArchaeologyError(f"Refusing overwrite: {md_path} (use --force)")
        md_content = render_report(payload)
    else:
        md_path = None

    # Write temps first, then replace, to reduce partial-final state when fmt="both".
    if json_path is not None and json_content is not None:
        atomic_write(json_path, json_content)
    if md_path is not None and md_content is not None:
        atomic_write(md_path, md_content)

    return json_path, md_path
