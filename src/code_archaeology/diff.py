from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from .utils import ArchaeologyError

def diff_reports(old_path: Path, new_path: Path) -> str:
    if not old_path.exists():
        raise ArchaeologyError(f"File not found: {old_path}")
    if not new_path.exists():
        raise ArchaeologyError(f"File not found: {new_path}")
        
    try:
        old_data = json.loads(old_path.read_text())
        new_data = json.loads(new_path.read_text())
    except json.JSONDecodeError as exc:
        raise ArchaeologyError(f"Failed to parse JSON: {exc}")
        
    old_pairs = {
        (p["file_a"], p["file_b"]): p 
        for p in old_data.get("detectors", {}).get("temporal_coupling", {}).get("pairs", [])
    }
    
    new_pairs = {
        (p["file_a"], p["file_b"]): p 
        for p in new_data.get("detectors", {}).get("temporal_coupling", {}).get("pairs", [])
    }
    
    added = []
    worsened = []
    improved = []
    removed = []
    
    for pair_key, new_p in new_pairs.items():
        if pair_key not in old_pairs:
            added.append(new_p)
        else:
            old_p = old_pairs[pair_key]
            if new_p["coupling_ratio"] > old_p["coupling_ratio"] or new_p["co_change_commits"] > old_p["co_change_commits"]:
                worsened.append((old_p, new_p))
            elif new_p["coupling_ratio"] < old_p["coupling_ratio"]:
                improved.append((old_p, new_p))
                
    for pair_key, old_p in old_pairs.items():
        if pair_key not in new_pairs:
            removed.append(old_p)
            
    # Markdown generation
    lines = [
        "# Code Archaeology Diff Report",
        "",
        f"- Old Report: {old_data.get('summary', {}).get('generated_at_utc', 'unknown')}",
        f"- New Report: {new_data.get('summary', {}).get('generated_at_utc', 'unknown')}",
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
    else:
        lines.append("- (none)")
        
    lines.extend(["", "## ✨ Resolved/Removed Coupling"])
    if removed:
        for p in removed:
             lines.append(f"- `{p['file_a']}` <-> `{p['file_b']}`")
    else:
        lines.append("- (none)")
        
    return "\n".join(lines) + "\n"
