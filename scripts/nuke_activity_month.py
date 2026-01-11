#!/usr/bin/env python3
"""
One-time utility to reset a monthly activity tab and repopulate X activity
from database/x_activity_log.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"


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


def month_tab_from_date(date_str: str, format_str: str) -> str | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if format_str == "MM/YYYY":
                return dt.strftime("%m/%Y")
            return dt.strftime("%m/%y")
        except ValueError:
            continue
    return None


def load_csv_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found at {csv_path}")
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row]


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset monthly activity tab from CSV.")
    parser.add_argument(
        "--month-tab",
        default="01/26",
        help="Month tab name to reset (default: 01/26).",
    )
    parser.add_argument(
        "--csv",
        default=str(PROJECT_ROOT / "database" / "x_activity_log.csv"),
        help="Path to x_activity_log.csv.",
    )
    args = parser.parse_args()

    env_path = DASHBOARD_DIR / ".env"
    activity_sheet_id = (
        os.getenv("ACTIVITY_SHEET_ID")
        or load_env_value(env_path, "ACTIVITY_SHEET_ID")
        or os.getenv("SPREADSHEET_ID")
        or load_env_value(env_path, "SPREADSHEET_ID")
    )
    if not activity_sheet_id:
        print("Missing ACTIVITY_SHEET_ID/SPREADSHEET_ID in environment.")
        return 1

    config_file = DASHBOARD_DIR / "sync_config.json"
    month_tab_format = "MM/YY"
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            month_tab_format = config.get("sync", {}).get("month_tab_format", month_tab_format)
        except Exception as exc:
            print(f"Warning: could not read sync_config.json: {exc}")

    credentials_file = PROJECT_ROOT / "shared" / "credentials" / "google.json"
    if not credentials_file.exists():
        print(f"Google credentials not found at {credentials_file}")
        return 1

    csv_path = Path(args.csv)
    rows = load_csv_rows(csv_path)

    filtered = []
    seen_urls = set()
    for row in rows:
        tab = month_tab_from_date(row.get("date", ""), month_tab_format)
        if tab != args.month_tab:
            continue
        activity_url = (row.get("activity_url") or "").strip()
        if not activity_url or activity_url in seen_urls:
            continue
        seen_urls.add(activity_url)
        filtered.append([
            row.get("date", ""),
            row.get("time", ""),
            row.get("discord_user", ""),
            row.get("x_handle", ""),
            row.get("activity_type", ""),
            activity_url,
            row.get("target_url", ""),
            row.get("task_id", ""),
            row.get("notes", ""),
        ])

    import gspread

    gc = gspread.service_account(filename=str(credentials_file))
    spreadsheet = gc.open_by_key(activity_sheet_id)

    try:
        worksheet = spreadsheet.worksheet(args.month_tab)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=args.month_tab, rows=2000, cols=23)

    worksheet.clear()

    x_headers = [
        "date",
        "time",
        "discord_user",
        "x_handle",
        "activity_type",
        "activity_url",
        "target_url",
        "task_id",
        "notes",
    ]
    reddit_headers = [
        "date",
        "time",
        "discord_user",
        "reddit_username",
        "activity_type",
        "activity_url",
        "target_url",
        "task_id",
        "upvotes",
        "comments",
        "notes",
    ]
    worksheet.update(range_name="A1:I1", values=[x_headers])
    worksheet.update(range_name="M1:W1", values=[reddit_headers])

    if not filtered:
        print("No CSV rows matched the requested month.")
        return 0

    end_row = len(filtered) + 1
    worksheet.update(
        range_name=f"A2:I{end_row}",
        values=filtered,
        value_input_option="RAW",
    )

    print(f"Reset {args.month_tab} and loaded {len(filtered)} X activity rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
