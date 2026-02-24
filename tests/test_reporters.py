from code_archaeology.reporters import render_report


def _minimal_payload() -> dict:
    return {
        "summary": {
            "repo_path": "repo",
            "head_commit": "abcdef1",
            "since_days": 30,
            "total_commits": 0,
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
        },
        "run_metadata": {"ignore_rules_applied": []},
        "actionability": {"top_actions": []},
        "notices": [],
        "detectors": {
            "abandoned_structures": [],
            "temporal_coupling": {"pairs": []},
            "era_segmentation": [],
        },
        "errors": [],
    }


def test_render_report_includes_empty_state_placeholders():
    out = render_report(_minimal_payload())

    assert "## Top High-Leverage Actions\n- (none)" in out
    assert "## Abandoned structures\n- (none)" in out
    assert "## Temporal coupling\n- (none)" in out
    assert "## Era segmentation\n- (none)" in out


def test_render_report_tolerates_missing_errors_key_for_older_payloads():
    payload = _minimal_payload()
    payload.pop("errors")

    out = render_report(payload)

    assert "# Code Archaeology Report" in out
    assert "## Errors" not in out
