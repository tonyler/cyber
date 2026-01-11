#!/usr/bin/env python3
"""
Normalize X/Twitter status URLs in database CSVs to https://x.com/i/status/{id}.
Dry-run by default; use --apply to write changes.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent
dashboard_dir = project_root / "dashboard"
sys.path.insert(0, str(dashboard_dir))

from csv_store import load_csv, write_csv


STATUS_RE = re.compile(r"/status(?:es)?/(\d+)")


def _looks_like_x_url(value: str) -> bool:
    lower = value.lower()
    return "x.com" in lower or "twitter.com" in lower


def normalize_x_status_url(value: str) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    if text.isdigit():
        return f"https://x.com/i/status/{text}"
    match = STATUS_RE.search(text)
    if match and _looks_like_x_url(text):
        return f"https://x.com/i/status/{match.group(1)}"
    if match and (text.startswith("http://") or text.startswith("https://")):
        # Fallback: still normalize if it looks like a URL with a status id.
        return f"https://x.com/i/status/{match.group(1)}"
    return None


def normalize_rows(
    rows: List[Dict[str, str]],
    url_fields: List[str],
    platform_field: Optional[str] = None,
    platform_value: Optional[str] = None,
    drop_missing_id: bool = False,
) -> Tuple[List[Dict[str, str]], int, int]:
    changed = 0
    skipped = 0
    kept_rows = []
    for row in rows:
        if platform_field and platform_value:
            if row.get(platform_field, "").lower() != platform_value:
                kept_rows.append(row)
                continue
        drop_row = False
        for field in url_fields:
            current = row.get(field, "")
            if not current:
                continue
            normalized = normalize_x_status_url(current)
            if normalized:
                if normalized != current:
                    row[field] = normalized
                    changed += 1
            else:
                if _looks_like_x_url(current) or current.isdigit():
                    skipped += 1
                    if drop_missing_id:
                        drop_row = True
                        break
        if not drop_row:
            kept_rows.append(row)
    return kept_rows, changed, skipped


def process_file(
    path: Path,
    url_fields: List[str],
    platform_field: Optional[str] = None,
    platform_value: Optional[str] = None,
    apply: bool = False,
    drop_missing_id: bool = False,
) -> Tuple[int, int]:
    fields, rows = load_csv(str(path))
    if not rows:
        return 0, 0
    rows, changed, skipped = normalize_rows(
        rows,
        url_fields,
        platform_field,
        platform_value,
        drop_missing_id=drop_missing_id,
    )
    if apply and changed:
        write_csv(str(path), fields, rows)
    return changed, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument(
        "--drop-missing-id",
        action="store_true",
        help="Drop rows with X URLs missing a status ID",
    )
    args = parser.parse_args()

    database_dir = project_root / "database"
    targets = [
        (database_dir / "links.csv", ["url"], "platform", "x"),
        (database_dir / "coordinated_tasks.csv", ["target_url"], "platform", "x"),
        (database_dir / "x_activity_log.csv", ["activity_url", "target_url"], None, None),
    ]

    total_changed = 0
    total_skipped = 0

    for path, url_fields, platform_field, platform_value in targets:
        if not path.exists():
            print(f"Skip missing: {path}")
            continue
        changed, skipped = process_file(
            path,
            url_fields,
            platform_field=platform_field,
            platform_value=platform_value,
            apply=args.apply,
            drop_missing_id=args.drop_missing_id,
        )
        total_changed += changed
        total_skipped += skipped
        mode = "APPLIED" if args.apply else "DRY-RUN"
        drop_note = " dropped-missing-id" if args.drop_missing_id else ""
        print(f"{mode} {path}: changed={changed} skipped={skipped}{drop_note}")

    print(f"Total changed: {total_changed}")
    print(f"Total skipped (non-canonical X URLs): {total_skipped}")
    if not args.apply:
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
