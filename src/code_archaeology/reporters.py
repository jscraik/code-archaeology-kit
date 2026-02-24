from __future__ import annotations
from collections import defaultdict
from typing import Any



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

    if ignore_rules:
        for rule in ignore_rules:
            lines.append(f"  - `{rule}`")
    else:
        lines.append("  - (none)")

    lines.extend(["", "## Top High-Leverage Actions"])
    if top_actions:
        for action in top_actions:
            lines.append(
                f"- [{action['priority']}] **{action['action']}** `{action['target']}` "
                f"(effort={action['effort']}, leverage={action['expected_leverage']}) — {action['rationale']}"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "## Abandoned structures"])
    abandoned_rows = payload["detectors"]["abandoned_structures"][:10]
    if abandoned_rows:
        for row in abandoned_rows:
            lines.append(
                f"- `{row['file']}` ({row['historical_commits']} commits, {row['days_since_last_change']}d stale, "
                f"class={row['path_class']}, confidence={row['confidence']})"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "## Temporal coupling"])
    temporal_rows = payload["detectors"]["temporal_coupling"]["pairs"][:10]
    if temporal_rows:
        for row in temporal_rows:
            log_coupled_flag = " 🔌 (logically coupled)" if row.get("is_logically_coupled") else ""
            lines.append(
                f"- `{row['file_a']}` <-> `{row['file_b']}` "
                f"(co-changes={row['co_change_commits']}, ratio={row['coupling_ratio']}, class={row['coupling_class']}){log_coupled_flag}"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "## Coupling classes"])
    class_counts: dict[str, int] = defaultdict(int)
    for row in payload["detectors"]["temporal_coupling"]["pairs"]:
        class_counts[row["coupling_class"]] += 1

    for coupling_class in ["suspicious", "risky", "expected"]:
        lines.append(f"- {coupling_class}: {class_counts.get(coupling_class, 0)}")

    lines.extend(["", "## Era segmentation"])
    eras = payload["detectors"]["era_segmentation"]
    if eras:
        for row in eras:
            lines.append(f"- {row['era']}: {row['label']} ({row['commits']} commits)")
    else:
        lines.append("- (none)")

    errors = payload.get("errors", [])
    if errors:
        lines.extend(["", "## Errors"])
        for error in errors:
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
