from __future__ import annotations

import argparse
import json
import time
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .analyze import ArchaeologyError, analyze_repo, write_payload, write_share_snippet
from .diff import diff_reports


def _append_event(output_dir: Path, event: dict[str, Any]) -> Path:
    output = output_dir.expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchaeologyError(f"Failed to prepare output directory: {output}") from exc

    path = output / "archaeology_events.jsonl"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError as exc:
        raise ArchaeologyError(f"Failed to write file: {path}") from exc
    return path


def main() -> int:
    parser = argparse.ArgumentParser(prog="cak", description="Code Archaeology Kit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan git repository and generate archaeology artifacts")
    scan.add_argument("--repo", type=Path, required=True)
    scan.add_argument("--since-days", type=int, default=365)
    scan.add_argument("--format", choices=["json", "md", "both"], default="both")
    scan.add_argument("--output-dir", type=Path, default=Path("."))
    scan.add_argument(
        "--share-snippet",
        action="store_true",
        help="Write a share-ready Markdown snippet (archaeology_share.md) plus a small local event log.",
    )
    scan.add_argument("--min-churn-threshold", type=int, default=3)
    scan.add_argument("--include-authors", action="store_true")
    scan.add_argument("--ack-pii", action="store_true")
    scan.add_argument(
        "--include-repo-path",
        action="store_true",
        help="Include the full resolved repo path in output (default: redacted to basename).",
    )
    scan.add_argument(
        "--include-commit-messages",
        action="store_true",
        help="Include commit messages in output (default: redacted).",
    )
    scan.add_argument("--ignore-glob", action="append", default=[], help="Glob pattern to exclude files from analysis (repeatable)")
    scan.add_argument("--no-ignore-defaults", action="store_true", help="Disable default ignore rules")
    scan.add_argument("--top-actions", type=int, default=3, help="Number of high-leverage actions in actionability output")
    scan.add_argument("--timeout-seconds", type=int, default=600)
    scan.add_argument("--max-commits", type=int, default=15000)
    scan.add_argument("--max-files-per-commit", type=int, default=40)
    scan.add_argument(
        "--large-commit-strategy",
        choices=["cap", "skip"],
        default="cap",
        help="How to handle commits touching > --max-files-per-commit files for temporal coupling (default: cap).",
    )
    scan.add_argument("--force", action="store_true")
    scan.add_argument("--json", action="store_true")

    diff_cmd = sub.add_parser("diff", help="Compare two local archaeology.json artifacts")
    diff_cmd.add_argument("--old", type=Path, required=True, help="Path to the older archaeology.json")
    diff_cmd.add_argument("--new", type=Path, required=True, help="Path to the newer archaeology.json")
    diff_cmd.add_argument("--output", type=Path, default=Path("."), help="Directory to emit archaeology_diff.md")

    args = parser.parse_args()

    if args.command == "scan":
        def emit_scan_error(
            message: str,
            json_path: Path | None = None,
            md_path: Path | None = None,
            share_path: Path | None = None,
            events_path: Path | None = None,
        ) -> int:
            if args.json:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "schema": "cak.scan.v1",
                            "artifacts": {
                                "json": str(json_path) if json_path else None,
                                "markdown": str(md_path) if md_path else None,
                            },
                            "share": {
                                "snippet_markdown": str(share_path) if share_path else None,
                                "events_jsonl": str(events_path) if events_path else None,
                            },
                            "top_actions": [],
                            "notices": [],
                            "errors": [{"code": "SCAN_ERROR", "message": message}],
                        },
                        indent=2,
                    )
                )
            else:
                print(f"error: {message}", file=sys.stderr)
            return 2

        if args.include_authors and not args.ack_pii:
            return emit_scan_error("--include-authors requires --ack-pii")
        if args.share_snippet and not args.force:
            share_target = args.output_dir.expanduser().resolve() / "archaeology_share.md"
            if share_target.exists() and share_target.is_dir():
                return emit_scan_error(f"Output path is a directory: {share_target}")
            if share_target.exists():
                return emit_scan_error(f"Refusing overwrite: {share_target} (use --force)")
        json_path: Path | None = None
        md_path: Path | None = None
        share_path: Path | None = None
        events_path: Path | None = None
        try:
            payload = analyze_repo(
                repo=args.repo,
                since_days=args.since_days,
                min_churn_threshold=args.min_churn_threshold,
                include_authors=args.include_authors,
                include_repo_path=args.include_repo_path,
                include_commit_messages=args.include_commit_messages,
                timeout_seconds=args.timeout_seconds,
                max_commits=args.max_commits,
                max_files_per_commit=args.max_files_per_commit,
                version=__version__,
                ignore_globs=args.ignore_glob,
                use_default_ignores=not args.no_ignore_defaults,
                top_actions=args.top_actions,
                large_commit_strategy=args.large_commit_strategy,
            )
            json_path, md_path = write_payload(payload, args.output_dir, args.format, args.force)
            if args.share_snippet:
                share_path = write_share_snippet(payload, args.output_dir, args.force)
                events_path = _append_event(
                    args.output_dir,
                    {
                        "schema": "cak.events.v1",
                        "name": "share_snippet_generated",
                        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "repo": payload.get("summary", {}).get("repo_path"),
                        "since_days": payload.get("summary", {}).get("since_days"),
                        "head": str(payload.get("summary", {}).get("head_commit", ""))[:7],
                    },
                )
        except ArchaeologyError as exc:
            return emit_scan_error(
                str(exc),
                json_path=json_path,
                md_path=md_path,
                share_path=share_path,
                events_path=events_path,
            )

        if args.json:
            print(json.dumps({
                "ok": True,
                "schema": "cak.scan.v1",
                "artifacts": {"json": str(json_path) if json_path else None, "markdown": str(md_path) if md_path else None},
                "share": {
                    "snippet_markdown": str(share_path) if args.share_snippet and share_path else None,
                    "events_jsonl": str(events_path) if args.share_snippet and events_path else None,
                },
                "top_actions": payload.get("actionability", {}).get("top_actions", []),
                "notices": payload.get("notices", []),
                "errors": payload.get("errors", []),
            }, indent=2))
        else:
            print(f"Scan complete: {args.repo}")
            if json_path:
                print(f"JSON: {json_path}")
            if md_path:
                print(f"Report: {md_path}")
            if args.share_snippet and share_path:
                print(f"Share snippet: {share_path}")
        return 0

    if args.command == "diff":
        try:
            diff_markdown = diff_reports(args.old, args.new)
            out_dir = args.output.expanduser().resolve()
            if out_dir.exists() and out_dir.is_file():
                raise ArchaeologyError(f"Output path is a file: {out_dir}")
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ArchaeologyError(f"Failed to prepare output directory: {out_dir}") from exc
            diff_path = out_dir / "archaeology_diff.md"
            with diff_path.open("w", encoding="utf-8") as handle:
                handle.write(diff_markdown)
            print(f"Diff complete. Generated: {diff_path}")
            return 0
        except ArchaeologyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    return 2
