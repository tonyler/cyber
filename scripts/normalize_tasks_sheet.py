#!/usr/bin/env python3
"""
One-time normalization for the tasks sheet monthly tab.
Ensures consistent column structure, header row, and removes malformed rows.
"""

import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime

import gspread

PROJECT_ROOT = Path("/root/cyber")
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
ENV_PATH = DASHBOARD_DIR / ".env"
CONFIG_PATH = DASHBOARD_DIR / "sync_config.json"

EXPECTED_HEADER = [
    "Date",
    "Author",
    "URL",
    "Impressions",
    "Likes",
    "Comments",
    "Notes",
    "Total Impressions",
    "Date",
    "Author",
    "URL",
    "Views",
    "Upvotes",
    "Comments",
    "Notes",
    "Total Impressions",
]


def load_env_value(env_path: Path, key: str) -> str:
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def current_month_tab() -> str:
    format_str = "MM/YY"
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text())
            format_str = config.get("sync", {}).get("month_tab_format", format_str)
        except Exception:
            pass

    now = datetime.utcnow()
    if format_str == "MM/YYYY":
        return now.strftime("%m/%Y")
    return now.strftime("%m/%y")


def _looks_like_url(value: str) -> bool:
    if not value:
        return False
    value = value.strip().lower()
    return value.startswith("http://") or value.startswith("https://") or "x.com" in value or "twitter.com" in value or "reddit.com" in value


def _pick_reddit_offset(row: list[str]) -> int:
    # Expected reddit URL index in canonical layout is 10 (column K).
    if len(row) > 10 and _looks_like_url(row[10]):
        return 8
    # Deprecated layout sometimes starts at column H (index 7).
    if len(row) > 9 and _looks_like_url(row[9]):
        return 7
    return 8


def _is_time_like(value: str) -> bool:
    if not value:
        return False
    value = value.strip()
    if ":" not in value:
        return False
    parts = value.split(":")
    if len(parts) not in (2, 3):
        return False
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return False
    return 0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59


def _is_activity_row(row: list[str]) -> bool:
    if len(row) < 6:
        return False
    time_value = row[1].strip() if len(row) > 1 and row[1] else ""
    activity_type = row[4].strip().lower() if len(row) > 4 and row[4] else ""
    if not _is_time_like(time_value):
        return False
    if activity_type not in {"comment", "quote", "repost", "retweet", "reply"}:
        return False
    return True


def normalize_row(row: list[str]) -> list[str]:
    normalized = [""] * 16
    if not row:
        return normalized

    # Normalize X columns (A:G) if present.
    for i in range(7):
        if i < len(row) and row[i]:
            normalized[i] = row[i]

    # Preserve X summary if already present.
    if len(row) > 7 and row[7]:
        normalized[7] = row[7]

    # Normalize Reddit columns; handle legacy offset.
    offset = _pick_reddit_offset(row)
    for i in range(7):
        src_index = offset + i
        dest_index = 8 + i
        if src_index < len(row) and row[src_index]:
            normalized[dest_index] = row[src_index]

    # Preserve Reddit summary if already present.
    if len(row) > 15 and row[15]:
        normalized[15] = row[15]

    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-id", default=None, help="Google Sheet ID for the tasks sheet")
    parser.add_argument("--tab", default="01/26", help="Month tab name to normalize (e.g. 01/26)")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--purge-activity", action="store_true", help="Remove activity-log rows from the tab")
    args = parser.parse_args()

    tasks_sheet_id = args.sheet_id or os.getenv("TASKS_SHEET_ID") or load_env_value(ENV_PATH, "TASKS_SHEET_ID")
    if not tasks_sheet_id:
        raise SystemExit("Missing TASKS_SHEET_ID in args, environment, or dashboard/.env")

    credentials_file = PROJECT_ROOT / "shared" / "credentials" / "google.json"
    if not credentials_file.exists():
        raise SystemExit(f"Missing credentials at {credentials_file}")

    if args.verbose:
        print("Loading gspread client...")
    start = time.perf_counter()
    client = gspread.service_account(filename=str(credentials_file))
    client.http_client.set_timeout(args.timeout)
    if args.verbose:
        print(f"Client created in {time.perf_counter() - start:.2f}s")
        print("Authenticating...")
    start = time.perf_counter()
    client.http_client.login()
    if args.verbose:
        print(f"Authenticated in {time.perf_counter() - start:.2f}s")

    month_tab = args.tab or current_month_tab()
    if args.verbose:
        print(f"Opening sheet {tasks_sheet_id} tab {month_tab}...")
    start = time.perf_counter()
    worksheet = client.open_by_key(tasks_sheet_id).worksheet(month_tab)
    if args.verbose:
        print(f"Sheet opened in {time.perf_counter() - start:.2f}s")

    if args.verbose:
        print("Fetching rows...")
    start = time.perf_counter()
    rows = worksheet.get_all_values()
    if args.verbose:
        print(f"Fetched {len(rows)} rows in {time.perf_counter() - start:.2f}s")
    if not rows:
        worksheet.update("A1:P1", [EXPECTED_HEADER], value_input_option="RAW")
        print("No data found; header written only.")
        return

    normalized_rows = [EXPECTED_HEADER]
    removed_rows = 0
    purged_rows = 0

    for i, row in enumerate(rows[1:], start=2):
        if row == EXPECTED_HEADER:
            removed_rows += 1
            continue

        if args.purge_activity and _is_activity_row(row):
            purged_rows += 1
            continue

        normalized = normalize_row(row)
        x_url = normalized[2].strip() if normalized[2] else ""
        reddit_url = normalized[10].strip() if normalized[10] else ""

        if not x_url and not reddit_url:
            removed_rows += 1
            continue

        normalized_rows.append(normalized)

    worksheet.update(f"A1:P{len(normalized_rows)}", normalized_rows, value_input_option="RAW")

    if len(rows) > len(normalized_rows):
        empty_rows = [[""] * 16 for _ in range(len(rows) - len(normalized_rows))]
        worksheet.update(
            f"A{len(normalized_rows) + 1}:P{len(rows)}",
            empty_rows,
            value_input_option="RAW",
        )

    print(f"Normalized rows: {len(normalized_rows) - 1}")
    print(f"Removed rows: {removed_rows}")
    if args.purge_activity:
        print(f"Purged activity rows: {purged_rows}")
    print(f"Sheet: {tasks_sheet_id} tab: {month_tab}")


if __name__ == "__main__":
    main()
