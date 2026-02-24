import json
from pathlib import Path
from code_archaeology.diff import diff_reports

def test_diff_reports_worsened_and_improved(tmp_path: Path):
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"
    
    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 5, "coupling_class": "risky"},
                    {"file_a": "c.py", "file_b": "d.py", "coupling_ratio": 0.9, "co_change_commits": 10, "coupling_class": "suspicious"},
                    {"file_a": "e.py", "file_b": "f.py", "coupling_ratio": 0.8, "co_change_commits": 8, "coupling_class": "suspicious"}
                ]
            }
        }
    }
    
    new_data = {
         "summary": {"generated_at_utc": "time2"},
         "detectors": {
             "temporal_coupling": {
                 "pairs": [
                     # a.py <-> b.py worsened (ratio increased)
                     {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.7, "co_change_commits": 6, "coupling_class": "risky"},
                     # c.py <-> d.py improved (ratio decreased)
                     {"file_a": "c.py", "file_b": "d.py", "coupling_ratio": 0.4, "co_change_commits": 10, "coupling_class": "risky"},
                     # w.py <-> z.py is new
                     {"file_a": "w.py", "file_b": "z.py", "coupling_ratio": 0.9, "co_change_commits": 4, "coupling_class": "suspicious"}
                     # e.py <-> f.py is removed
                 ]
             }
         }
    }
    
    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))
    
    result = diff_reports(old_json, new_json)
    
    assert "## 📈 Worsened Coupling" in result
    assert "a.py" in result and "b.py" in result
    assert "0.5 -> **0.7**" in result
    
    assert "## 🚨 New Coupling Pairs" in result
    assert "w.py" in result and "z.py" in result
    
    assert "## 📉 Improved Coupling" in result
    assert "c.py" in result and "d.py" in result
    assert "0.9 -> **0.4**" in result
    
    assert "## ✨ Resolved/Removed Coupling" in result
    assert "e.py" in result and "f.py" in result

def test_diff_missing_file(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest
    
    with pytest.raises(ArchaeologyError):
        diff_reports(tmp_path / "missing", tmp_path / "also_missing")


def test_diff_reports_rejects_malformed_pair_entries(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {"temporal_coupling": {"pairs": [{"file_a": "a.py", "coupling_ratio": 0.5}]}}
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}}
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_pairs_missing_metrics(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {"temporal_coupling": {"pairs": [{"file_a": "a.py", "file_b": "b.py"}]}}
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": [{"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.2, "co_change_commits": 1}]}}
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_non_utf8_input(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_json.write_bytes(b"\xff\xfe\x00\x00")
    new_json.write_text(json.dumps({"summary": {}, "detectors": {"temporal_coupling": {"pairs": []}}}))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_non_object_json(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_json.write_text("[]")
    new_json.write_text("{}")

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_non_object_detector_nodes(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    new_data = {"summary": {}, "detectors": {"temporal_coupling": {"pairs": []}}}

    old_json.write_text(json.dumps({"summary": {}, "detectors": []}))
    new_json.write_text(json.dumps(new_data))
    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)

    old_json.write_text(json.dumps({"summary": {}, "detectors": {"temporal_coupling": []}}))
    new_json.write_text(json.dumps(new_data))
    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_missing_required_detector_keys(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_json.write_text(json.dumps({"summary": {}}))
    new_json.write_text(json.dumps({"summary": {}, "detectors": {"temporal_coupling": {"pairs": []}}}))
    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)

    old_json.write_text(json.dumps({"summary": {}, "detectors": {}}))
    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)

    old_json.write_text(json.dumps({"summary": {}, "detectors": {"temporal_coupling": {}}}))
    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_non_object_summary(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_json.write_text(json.dumps({"summary": [], "detectors": {"temporal_coupling": {"pairs": []}}}))
    new_json.write_text(json.dumps({"summary": {}, "detectors": {"temporal_coupling": {"pairs": []}}}))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_missing_summary(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_json.write_text(json.dumps({"detectors": {"temporal_coupling": {"pairs": []}}}))
    new_json.write_text(json.dumps({"summary": {}, "detectors": {"temporal_coupling": {"pairs": []}}}))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_detects_class_only_worsening(tmp_path: Path):
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 5, "coupling_class": "expected"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 5, "coupling_class": "risky"}
                ]
            }
        },
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))
    result = diff_reports(old_json, new_json)

    assert "## 📈 Worsened Coupling" in result
    assert "`a.py` <-> `b.py`" in result


def test_diff_reports_rejects_duplicate_pairs_in_single_report(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 5, "coupling_class": "risky"},
                    {"file_a": "b.py", "file_b": "a.py", "coupling_ratio": 0.6, "co_change_commits": 6, "coupling_class": "suspicious"},
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_invalid_metric_ranges(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 1.2, "co_change_commits": -1, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_zero_cochange_counts(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.2, "co_change_commits": 0, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_single_cochange_counts(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.2, "co_change_commits": 1, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_non_finite_ratio_values(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": float("nan"), "co_change_commits": 2, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_boolean_metrics(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": True, "co_change_commits": False, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_unknown_coupling_class(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.2, "co_change_commits": 2, "coupling_class": "unknown"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_self_pairs(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "a.py", "coupling_ratio": 0.4, "co_change_commits": 2, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_rejects_empty_file_names(tmp_path: Path):
    from code_archaeology.utils import ArchaeologyError
    import pytest

    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "", "file_b": "b.py", "coupling_ratio": 0.4, "co_change_commits": 2, "coupling_class": "risky"}
                ]
            }
        },
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    with pytest.raises(ArchaeologyError):
        diff_reports(old_json, new_json)


def test_diff_reports_treats_reversed_pairs_as_same_pair(tmp_path: Path):
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 5, "coupling_class": "risky"}
                ]
            }
        }
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "b.py", "file_b": "a.py", "coupling_ratio": 0.5, "co_change_commits": 5, "coupling_class": "risky"}
                ]
            }
        }
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))
    result = diff_reports(old_json, new_json)

    assert "## 🚨 New Coupling Pairs\n- (none)" in result
    assert "## ✨ Resolved/Removed Coupling\n- (none)" in result


def test_diff_reports_marks_cochange_drop_as_improved(tmp_path: Path):
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 8, "coupling_class": "risky"}
                ]
            }
        }
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "a.py", "file_b": "b.py", "coupling_ratio": 0.5, "co_change_commits": 4, "coupling_class": "risky"}
                ]
            }
        }
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))
    result = diff_reports(old_json, new_json)

    assert "## 📉 Improved Coupling" in result
    assert "a.py" in result and "b.py" in result


def test_diff_reports_sorts_section_entries_for_stable_output(tmp_path: Path):
    old_json = tmp_path / "old.json"
    new_json = tmp_path / "new.json"

    old_data = {
        "summary": {"generated_at_utc": "time1"},
        "detectors": {"temporal_coupling": {"pairs": []}},
    }
    new_data = {
        "summary": {"generated_at_utc": "time2"},
        "detectors": {
            "temporal_coupling": {
                "pairs": [
                    {"file_a": "z.py", "file_b": "a.py", "coupling_ratio": 0.7, "co_change_commits": 5, "coupling_class": "risky"},
                    {"file_a": "b.py", "file_b": "c.py", "coupling_ratio": 0.7, "co_change_commits": 5, "coupling_class": "risky"},
                ]
            }
        },
    }

    old_json.write_text(json.dumps(old_data))
    new_json.write_text(json.dumps(new_data))

    result = diff_reports(old_json, new_json)
    b_index = result.index("`b.py` <-> `c.py`")
    z_index = result.index("`z.py` <-> `a.py`")
    assert b_index < z_index
