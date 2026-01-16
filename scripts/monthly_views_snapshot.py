#!/usr/bin/env python3
"""
Create daily snapshots of the current month total views and record each day's increment.

This script:
1. Loads the canonical links CSV under `database/links.csv`.
2. Sums all `impressions` for the current year-month.
3. Stores or updates a monthly CSV (`database/monthly_views/YYYY-MM-views.csv`)
   with columns: date, total_views, difference.
4. Difference is computed against the previous snapshot for the month.
"""

from __future__ import annotations

import csv
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "shared"))

from config import DATABASE_DIR, load_env

load_env()

TASKS_FILE = DATABASE_DIR / "links.csv"
VIEWS_DIR = DATABASE_DIR / "monthly_views"
VIEWS_DIR.mkdir(parents=True, exist_ok=True)
LOG = logging.getLogger("monthly-views")

FIELDNAMES = ["date", "total_views", "difference"]


def _as_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        cleaned = str(value).replace(",", "").strip()
        return int(float(cleaned))
    except ValueError:
        return 0


def _row_to_month(row: dict[str, str]) -> str | None:
    if row.get("year_month"):
        return row["year_month"]

    created = row.get("created_date") or row.get("date")
    if not created:
        return None

    for fmt in ("%Y-%m", "%Y-%m-%d"):
        try:
            return datetime.strptime(created, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None


def _load_tasks() -> Iterable[dict[str, str]]:
    if not TASKS_FILE.exists():
        LOG.warning("Tasks file missing at %s; no views snapshot created.", TASKS_FILE)
        return []
    with TASKS_FILE.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _monthly_total(month: str, rows: Iterable[dict[str, str]]) -> int:
    total = 0
    for row in rows:
        if _row_to_month(row) != month:
            continue
        total += _as_int(row.get("impressions"))
    return total


def _load_snapshot(path: Path) -> List[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def _write_snapshot(path: Path, rows: List[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sorted_rows(rows: Iterable[dict[str, str]]) -> List[dict[str, str]]:
    def key(row: dict[str, str]) -> str:
        return row.get("date", "")
    return sorted(rows, key=key)


def _previous_total(rows: Iterable[dict[str, str]], today: str) -> int:
    total = 0
    for row in _sorted_rows(rows):
        row_date = row.get("date")
        if not row_date or row_date >= today:
            continue
        total = _as_int(row.get("total_views"))
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    today = date.today()
    month_key = today.strftime("%Y-%m")
    snapshot_file = VIEWS_DIR / f"{month_key}-views.csv"

    tasks = _load_tasks()
    total_views = _monthly_total(month_key, tasks)

    rows = _load_snapshot(snapshot_file)
    previous_total = _previous_total(rows, today.strftime("%Y-%m-%d"))
    difference = total_views - previous_total

    today_row = {
        "date": today.strftime("%Y-%m-%d"),
        "total_views": str(total_views),
        "difference": str(difference),
    }

    rows_by_date = {row.get("date", ""): row for row in rows if row.get("date")}
    rows_by_date[today_row["date"]] = today_row

    updated_rows = _sorted_rows(rows_by_date.values())
    _write_snapshot(snapshot_file, updated_rows)

    LOG.info("Recorded views snapshot for %s: total=%d (Δ=%d)", today_row["date"], total_views, difference)


if __name__ == "__main__":
    main()
