"""Local CLI browser for the System B source index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .index_store import DEFAULT_SOURCES_INDEX, find_by_thread, find_source, list_failures, list_recent


def _adapter(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") or {}
    decision = metadata.get("adapter_decision") or {}
    return str(decision.get("primary") or metadata.get("acquisition_method") or record.get("acquisition_method") or "_unknown_")


def _row(record: dict[str, Any]) -> str:
    key = record.get("source_key") or record.get("normalized_url") or record.get("url") or "_unknown_"
    source = record.get("source_type") or record.get("platform") or "_unknown_"
    title = record.get("title") or record.get("canonical_name") or record.get("url") or ""
    status = record.get("status") or "indexed"
    error = record.get("error") or record.get("errors") or ""
    return f"{key}\t{source}\t{status}\t{title}\t{error}" if error else f"{key}\t{source}\t{status}\t{title}"


def _print_records(records: list[dict[str, Any]], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(records, indent=2, ensure_ascii=False, default=str))
        return
    for record in records:
        print(_row(record))


def render_diagnostics(records: list[dict[str, Any]], *, thread_id: str | None = None) -> str:
    lines = ["# System B Diagnostics", ""]
    if thread_id:
        lines.extend([f"- Thread: {thread_id}", ""])
    if not records:
        lines.extend(["No matching source index records found.", "Next action: confirm the backend hook upserted the source index."])
        return "\n".join(lines) + "\n"

    for idx, record in enumerate(records, start=1):
        metadata = record.get("metadata") or {}
        lines.extend(
            [
                f"## Source {idx}",
                "",
                f"- Source key: {record.get('source_key') or '_missing_'}",
                f"- Source URL: {record.get('url') or record.get('normalized_url') or '_missing_'}",
                f"- Adapter: {_adapter(record)}",
                f"- Fallback warnings: {metadata.get('adapter_warnings') or record.get('adapter_warnings') or []}",
                f"- Source storage: {record.get('source_dir') or '_missing_'}",
                f"- Manifest: {record.get('latest_manifest_path') or record.get('manifest_path') or '_missing_'}",
                f"- Media kind: {metadata.get('media_kind') or record.get('media_kind') or '_unknown_'}",
                f"- Transcript: {metadata.get('transcript_status') or record.get('transcript_status') or '_unknown_'}",
                f"- Frames: {metadata.get('frame_count') if metadata.get('frame_count') is not None else record.get('frame_count', '_unknown_')}",
                f"- Source index: indexed",
                f"- Errors: {record.get('error') or record.get('errors') or []}",
                "",
            ]
        )
        if record.get("error") or record.get("errors"):
            lines.extend(["Next action: inspect adapter stderr and retry with the alternate adapter if available.", ""])
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="system-b-index")
    parser.add_argument("--index", default=str(DEFAULT_SOURCES_INDEX), help="Path to sources.jsonl")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--json", action="store_true")

    show_parser = sub.add_parser("show")
    show_parser.add_argument("query")
    show_parser.add_argument("--json", action="store_true")

    failures_parser = sub.add_parser("failures")
    failures_parser.add_argument("--limit", type=int, default=20)
    failures_parser.add_argument("--json", action="store_true")

    thread_parser = sub.add_parser("thread")
    thread_parser.add_argument("thread_id")
    thread_parser.add_argument("--json", action="store_true")

    diagnostics_parser = sub.add_parser("diagnostics")
    diagnostics_parser.add_argument("--thread-id")
    diagnostics_parser.add_argument("--source")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.index)

    if args.command == "list":
        _print_records(list_recent(args.limit, path=path), as_json=args.json)
        return 0
    if args.command == "show":
        record = find_source(args.query, path=path)
        if not record:
            print(f"source not found: {args.query}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
        else:
            print(_row(record))
        return 0
    if args.command == "failures":
        _print_records(list_failures(args.limit, path=path), as_json=args.json)
        return 0
    if args.command == "thread":
        _print_records(find_by_thread(args.thread_id, path=path), as_json=args.json)
        return 0
    if args.command == "diagnostics":
        if args.thread_id:
            records = find_by_thread(args.thread_id, path=path)
        elif args.source:
            record = find_source(args.source, path=path)
            records = [record] if record else []
        else:
            records = list_recent(1, path=path)
        print(render_diagnostics(records, thread_id=args.thread_id), end="")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
