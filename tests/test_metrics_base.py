from code_archaeology.metrics import compute_base_metrics
from code_archaeology.models import Commit, FileChange
from code_archaeology.metrics import abandoned_structures
from code_archaeology.metrics import build_dig_plan
from code_archaeology.metrics import rerank_top_actions
from datetime import datetime, timezone, timedelta
import pytest


def test_compute_base_metrics_classifies_modern_js_and_ts_extensions() -> None:
    commits = [
        Commit(
            hash="a" * 40,
            date="2026-01-01T00:00:00+00:00",
            author_name="Test",
            author_email="test@example.com",
            message="feat: add modules",
            files=[
                FileChange(path="src/main.mjs", additions=1, deletions=0),
                FileChange(path="src/legacy.cjs", additions=1, deletions=0),
                FileChange(path="src/types.mts", additions=1, deletions=0),
                FileChange(path="src/node.cts", additions=1, deletions=0),
            ],
        )
    ]

    metrics = compute_base_metrics(commits, include_authors=False, include_commit_messages=False)
    language_counts = {row["language"]: row["commits"] for row in metrics["language_breakdown"]}

    assert language_counts["JavaScript"] == 1
    assert language_counts["TypeScript"] == 1


def test_compute_base_metrics_classifies_jsx_as_javascript() -> None:
    commits = [
        Commit(
            hash="b" * 40,
            date="2026-01-01T00:00:00+00:00",
            author_name="Test",
            author_email="test@example.com",
            message="feat: add component",
            files=[FileChange(path="src/component.jsx", additions=1, deletions=0)],
        )
    ]

    metrics = compute_base_metrics(commits, include_authors=False, include_commit_messages=False)
    language_counts = {row["language"]: row["commits"] for row in metrics["language_breakdown"]}
    assert language_counts["JavaScript"] == 1


def test_abandoned_structures_applies_low_value_penalty_to_root_markdown() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=180)
    commits = [
        Commit(
            hash="c" * 40,
            date=old.isoformat(),
            author_name="Test",
            author_email="test@example.com",
            message="docs: add readme",
            files=[FileChange(path="README.md", additions=10, deletions=0)],
            date_obj=old,
        )
    ]

    out = abandoned_structures(commits, min_churn=1, stale_days=90)
    row = next(r for r in out if r["file"] == "README.md")
    assert "penalty=0.2" in row["confidence_explainer"]


def test_abandoned_structures_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError):
        abandoned_structures([], min_churn=0, stale_days=90)
    with pytest.raises(ValueError):
        abandoned_structures([], min_churn=1, stale_days=-1)


def test_abandoned_structures_applies_low_value_penalty_to_root_issue_template() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=180)
    commits = [
        Commit(
            hash="d" * 40,
            date=old.isoformat(),
            author_name="Test",
            author_email="test@example.com",
            message="docs: add template",
            files=[FileChange(path="ISSUE_TEMPLATE/config.yml", additions=5, deletions=0)],
            date_obj=old,
        )
    ]

    out = abandoned_structures(commits, min_churn=1, stale_days=90)
    row = next(r for r in out if r["file"] == "ISSUE_TEMPLATE/config.yml")
    assert "penalty=0.2" in row["confidence_explainer"]


def test_build_dig_plan_respects_requested_top_actions_above_ten() -> None:
    payload = {
        "detectors": {
            "abandoned_structures": [
                {
                    "file": f"src/abandoned_{i}.py",
                    "path_class": "product",
                    "historical_commits": 3 + i,
                    "days_since_last_change": 90 + i,
                    "confidence": "high",
                }
                for i in range(20)
            ],
            "temporal_coupling": {
                "pairs": [
                    {
                        "file_a": f"src/a_{i}.py",
                        "file_b": f"src/b_{i}.py",
                        "co_change_commits": 2 + i,
                        "coupling_ratio": 0.5,
                        "coupling_class": "risky",
                    }
                    for i in range(20)
                ]
            },
        },
        "base_metrics": {"file_churn": []},
    }

    actions = build_dig_plan(payload, top_actions=12)
    assert len(actions) == 12


def test_rerank_top_actions_is_deterministic_for_equal_scores() -> None:
    raw_actions = [
        {
            "priority": "high",
            "action": "review_temporal_coupling",
            "target": "src/a.py <-> src/b.py",
            "effort": "medium",
            "expected_leverage": "high",
            "rationale": "alpha",
        },
        {
            "priority": "high",
            "action": "review_temporal_coupling",
            "target": "src/c.py <-> src/d.py",
            "effort": "medium",
            "expected_leverage": "high",
            "rationale": "beta",
        },
    ]

    ranked_a, changes_a = rerank_top_actions(raw_actions, baseline_actions=[], top_actions=2, annotate_reasons=True)
    ranked_b, changes_b = rerank_top_actions(raw_actions, baseline_actions=[], top_actions=2, annotate_reasons=True)

    assert ranked_a == ranked_b
    assert changes_a == changes_b
    assert all("adaptive_reason=" in row["rationale"] for row in ranked_a)


def test_rerank_top_actions_tracks_promotions_and_demotions() -> None:
    raw_actions = [
        {
            "priority": "high",
            "action": "review_temporal_coupling",
            "target": "src/known.py <-> src/known2.py",
            "effort": "medium",
            "expected_leverage": "high",
            "rationale": "known",
        },
        {
            "priority": "medium",
            "action": "review_high_churn_file",
            "target": "src/new.py",
            "effort": "low",
            "expected_leverage": "high",
            "rationale": "new",
        },
    ]
    baseline_actions = [
        {
            "priority": "high",
            "action": "review_temporal_coupling",
            "target": "src/known.py <-> src/known2.py",
            "effort": "medium",
            "expected_leverage": "high",
            "rationale": "known",
        }
    ]

    ranked, changes = rerank_top_actions(raw_actions, baseline_actions=baseline_actions, top_actions=1)
    assert ranked[0]["target"] == "src/new.py"
    assert len(changes) >= 1
