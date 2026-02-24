from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any

from .utils import ArchaeologyError


def _pair_key(file_a: str, file_b: str) -> tuple[str, str]:
    return tuple(sorted((file_a, file_b)))


def _class_severity(coupling_class: str) -> int:
    return {"expected": 0, "risky": 1, "suspicious": 2}.get(coupling_class, -1)


def _is_non_bool_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_pairs(data: dict[str, Any], label: str) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(data, dict):
        raise ArchaeologyError(f"Invalid {label} report: top-level JSON must be an object")

    if "detectors" not in data:
        raise ArchaeologyError(f"Invalid {label} report: missing detectors")
    detectors = data.get("detectors")
    if not isinstance(detectors, dict):
        raise ArchaeologyError(f"Invalid {label} report: detectors must be an object")

    if "temporal_coupling" not in detectors:
        raise ArchaeologyError(f"Invalid {label} report: missing detectors.temporal_coupling")
    temporal = detectors.get("temporal_coupling")
    if not isinstance(temporal, dict):
        raise ArchaeologyError(f"Invalid {label} report: detectors.temporal_coupling must be an object")

    if "pairs" not in temporal:
        raise ArchaeologyError(f"Invalid {label} report: missing detectors.temporal_coupling.pairs")
    raw_pairs = temporal.get("pairs")
    if not isinstance(raw_pairs, list):
        raise ArchaeologyError(f"Invalid {label} report: detectors.temporal_coupling.pairs must be a list")

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, pair in enumerate(raw_pairs):
        if not isinstance(pair, dict):
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} must be an object")
        file_a = pair.get("file_a")
        file_b = pair.get("file_b")
        if not isinstance(file_a, str) or not isinstance(file_b, str):
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} missing file_a/file_b")
        if not file_a or not file_b:
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} has empty file_a/file_b")
        if file_a == file_b:
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} must reference two distinct files")
        ratio = pair.get("coupling_ratio")
        co_changes = pair.get("co_change_commits")
        coupling_class = pair.get("coupling_class")
        if (
            not _is_non_bool_number(ratio)
            or not isinstance(co_changes, int)
            or isinstance(co_changes, bool)
            or not isinstance(coupling_class, str)
        ):
            raise ArchaeologyError(
                f"Invalid {label} report: pair at index {idx} missing coupling_ratio/co_change_commits/coupling_class"
            )
        if ratio < 0 or ratio > 1:
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} has coupling_ratio outside [0,1]")
        if not math.isfinite(ratio):
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} has non-finite coupling_ratio")
        if co_changes < 2:
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} has co_change_commits < 2")
        if coupling_class not in {"expected", "risky", "suspicious"}:
            raise ArchaeologyError(f"Invalid {label} report: pair at index {idx} has unknown coupling_class")
        key = _pair_key(file_a, file_b)
        if key in out:
            raise ArchaeologyError(f"Invalid {label} report: duplicate pair for {key[0]} <-> {key[1]}")
        out[key] = pair
    return out


def _summary_generated_at(data: dict[str, Any], label: str) -> str:
    if "summary" not in data:
        raise ArchaeologyError(f"Invalid {label} report: missing summary")
    summary = data.get("summary")
    if not isinstance(summary, dict):
        raise ArchaeologyError(f"Invalid {label} report: summary must be an object")
    generated = summary.get("generated_at_utc", "unknown")
    return generated if isinstance(generated, str) else "unknown"


def diff_reports(old_path: Path, new_path: Path) -> str:
    if not old_path.exists():
        raise ArchaeologyError(f"File not found: {old_path}")
    if not new_path.exists():
        raise ArchaeologyError(f"File not found: {new_path}")
        
    try:
        old_data = json.loads(old_path.read_text())
        new_data = json.loads(new_path.read_text())
    except (UnicodeDecodeError, OSError) as exc:
        raise ArchaeologyError(f"Failed to read report file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ArchaeologyError(f"Failed to parse JSON: {exc}") from exc
        
    old_pairs = _parse_pairs(old_data, "old")
    new_pairs = _parse_pairs(new_data, "new")
    
    added = []
    worsened = []
    improved = []
    removed = []
    
    for pair_key, new_p in new_pairs.items():
        if pair_key not in old_pairs:
            added.append(new_p)
        else:
            old_p = old_pairs[pair_key]
            old_severity = _class_severity(old_p["coupling_class"])
            new_severity = _class_severity(new_p["coupling_class"])
            if (
                new_p["coupling_ratio"] > old_p["coupling_ratio"]
                or new_p["co_change_commits"] > old_p["co_change_commits"]
                or new_severity > old_severity
            ):
                worsened.append((old_p, new_p))
            elif (
                new_p["coupling_ratio"] < old_p["coupling_ratio"]
                or new_p["co_change_commits"] < old_p["co_change_commits"]
                or new_severity < old_severity
            ):
                improved.append((old_p, new_p))
                
    for pair_key, old_p in old_pairs.items():
        if pair_key not in new_pairs:
            removed.append(old_p)

    worsened.sort(key=lambda pair: (pair[1]["file_a"], pair[1]["file_b"]))
    improved.sort(key=lambda pair: (pair[1]["file_a"], pair[1]["file_b"]))
    added.sort(key=lambda pair: (pair["file_a"], pair["file_b"]))
    removed.sort(key=lambda pair: (pair["file_a"], pair["file_b"]))
            
    # Markdown generation
    lines = [
        "# Code Archaeology Diff Report",
        "",
        f"- Old Report: {_summary_generated_at(old_data, 'old')}",
        f"- New Report: {_summary_generated_at(new_data, 'new')}",
        ""
    ]
    
    lines.append("## 📈 Worsened Coupling")
    if worsened:
        for old_p, new_p in worsened:
            lines.append(f"- `{new_p['file_a']}` <-> `{new_p['file_b']}`")
            lines.append(f"  - Ratio: {old_p['coupling_ratio']} -> **{new_p['coupling_ratio']}**")
            lines.append(f"  - Co-changes: {old_p['co_change_commits']} -> **{new_p['co_change_commits']}**")
    else:
        lines.append("- (none)")
        
    lines.extend(["", "## 🚨 New Coupling Pairs"])
    if added:
        for p in added:
            lines.append(f"- `{p['file_a']}` <-> `{p['file_b']}` (ratio={p['coupling_ratio']}, class={p['coupling_class']})")
    else:
        lines.append("- (none)")
        
    lines.extend(["", "## 📉 Improved Coupling"])
    if improved:
        for old_p, new_p in improved:
            lines.append(f"- `{new_p['file_a']}` <-> `{new_p['file_b']}`")
            lines.append(f"  - Ratio: {old_p['coupling_ratio']} -> **{new_p['coupling_ratio']}**")
            lines.append(f"  - Co-changes: {old_p['co_change_commits']} -> **{new_p['co_change_commits']}**")
    else:
        lines.append("- (none)")
        
    lines.extend(["", "## ✨ Resolved/Removed Coupling"])
    if removed:
        for p in removed:
             lines.append(f"- `{p['file_a']}` <-> `{p['file_b']}`")
    else:
        lines.append("- (none)")
        
    return "\n".join(lines) + "\n"
