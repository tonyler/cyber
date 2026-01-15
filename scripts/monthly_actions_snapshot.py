#!/usr/bin/env python3
"""
Create daily snapshots of contributions (comments + quotes + retweets) for the current month.

This script:
1. Reads X and Reddit activity logs from `database/x_activity_log.csv` and `database/reddit_activity_log.csv`.
2. Counts qualifying activity types per day for the current month.
3. Stores/updates `database/monthly_actions/YYYY-MM-actions.csv` with `date,total_actions,difference`.
4. Difference reflects the incremental actions captured that day.
"""

from __future__ import annotations

import csv
import logging
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "shared"))

from config import DATABASE_DIR, load_env

load_env()

LOG = logging.getLogger("monthly-actions")
FIELDNAMES = ["date", "total_actions", "difference"]
ACTIONS_DIR = DATABASE_DIR / "monthly_actions"
ACTIONS_DIR.mkdir(parents=True, exist_ok=True)

ACTIVITY_FILES: Tuple[Path, Tuple[str, ...]] = (
    (DATABASE_DIR / "x_activity_log.csv", ("comment", "reply", "quote", "retweet", "repost")),
    (DATABASE_DIR / "reddit_activity_log.csv", ("comment", "reply",)),
)


def _parse_month(date_str: str) -> str | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None


def _load_activity_rows(path: Path) -> Iterable[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _aggregate_actions(month_key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for path, allowed in ACTIVITY_FILES:
        for row in _load_activity_rows(path):
            row_month = _parse_month(row.get("date", "") or row.get("created_date", ""))
            if row_month != month_key:
                continue
            activity_type = (row.get("activity_type") or "").lower()
            if activity_type not in allowed:
                continue
            day = row.get("date") or row.get("created_date")
            if not day:
                continue
            normalized = day.strip()
            counts[normalized] += 1
    return counts


def _load_snapshot(path: Path) -> List[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _write_snapshot(path: Path, rows: List[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sorted_rows(rows: Iterable[dict[str, str]]) -> List[dict[str, str]]:
    return sorted(rows, key=lambda r: r.get("date", ""))


def _previous_total(rows: Iterable[dict[str, str]], today: str) -> int:
    total = 0
    for row in _sorted_rows(rows):
        if not row.get("date") or row["date"] >= today:
            continue
        total = int(row.get("total_actions", "0") or "0")
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    today_obj = date.today()
    month_key = today_obj.strftime("%Y-%m")
    snapshot_path = ACTIONS_DIR / f"{month_key}-actions.csv"

    counts = _aggregate_actions(month_key)
    total_actions = sum(counts.values())

    rows = _load_snapshot(snapshot_path)
    previous = _previous_total(rows, today_obj.strftime("%Y-%m-%d"))
    difference = total_actions - previous

    today_row = {
        "date": today_obj.strftime("%Y-%m-%d"),
        "total_actions": str(total_actions),
        "difference": str(difference),
    }

    by_date = {row.get("date", ""): row for row in rows if row.get("date")}
    by_date[today_row["date"]] = today_row

    updated_rows = _sorted_rows(by_date.values())
    _write_snapshot(snapshot_path, updated_rows)

    LOG.info("Recorded actions snapshot for %s: total=%d (Δ=%d)", today_row["date"], total_actions, difference)


if __name__ == "__main__":
    main()
