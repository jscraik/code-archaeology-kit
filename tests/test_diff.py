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
