"""Shared test helpers — NOT a conftest. Importable as 'helpers' in tests."""
import csv
from pathlib import Path

MEMBERS_FIELDNAMES = [
    "discord_user", "x_handle", "reddit_username", "status",
    "joined_date", "last_activity", "total_points", "last_active",
    "total_tasks", "x_profile_url", "reddit_profile_url", "registration_date",
]

LINKS_FIELDNAMES = [
    "id", "platform", "url", "author", "year_month", "date",
    "impressions", "likes", "comments", "retweets", "content", "title", "synced_at",
]

X_ACTIVITY_FIELDNAMES = [
    "date", "time", "discord_user", "x_handle", "activity_type",
    "activity_url", "target_url", "task_id", "notes",
]

REDDIT_ACTIVITY_FIELDNAMES = [
    "date", "time", "discord_user", "reddit_username", "activity_type",
    "activity_url", "target_url", "task_id", "notes",
]


def write_csv(path: Path, fieldnames: list, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
