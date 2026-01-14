#!/usr/bin/env python3
"""
Sync Worker - Periodically syncs data from Google Sheets to local database
"""

import sys
import time
import json
import csv
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# Add paths
project_root = Path(__file__).resolve().parent.parent
dashboard_dir = project_root / "dashboard"
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(dashboard_dir))

from config import (
    PROJECT_ROOT,
    CREDENTIALS_FILE,
    members_sheet_id as get_members_sheet_id,
    tasks_sheet_id as get_tasks_sheet_id,
    activity_sheet_id as get_activity_sheet_id,
    load_env,
)
from logger_config import setup_logger

load_env()

logger = setup_logger(__name__)

# Load config
config_file = dashboard_dir / "sync_config.json"
try:
    with open(config_file) as f:
        config = json.load(f)
    sync_config = config.get('sync', {})
    interval_minutes = sync_config.get('interval_minutes', 30)
    enabled = sync_config.get('enabled', True)
except Exception as e:
    logger.warning(f"Could not load sync config: {e}, using defaults")
    interval_minutes = 30
    enabled = True

def _fetch_sheet(spreadsheet, sheet_name: str, range_name: str = None):
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except Exception as e:
        logger.warning(f"Sheet '{sheet_name}' not found: {e}")
        return []

    try:
        return worksheet.get(range_name) if range_name else worksheet.get_all_values()
    except Exception as e:
        logger.error(f"Failed to fetch data from '{sheet_name}': {e}")
        return []

def _current_month_tab(format_str: str) -> str:
    now = datetime.utcnow()
    if format_str == "MM/YY":
        return now.strftime("%m/%y")
    if format_str == "MM/YYYY":
        return now.strftime("%m/%Y")
    return now.strftime("%m/%y")

def _month_tab_to_year_month(month_tab: str) -> str:
    try:
        if "/" in month_tab:
            month, year = month_tab.split("/", 1)
            if len(year) == 2:
                year = f"20{year}"
            return f"{year}-{month.zfill(2)}"
    except Exception:
        pass
    return datetime.utcnow().strftime("%Y-%m")

def _month_tab_from_date(date_str: str, format_str: str) -> str:
    if date_str:
        for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if format_str == "MM/YYYY":
                    return dt.strftime("%m/%Y")
                return dt.strftime("%m/%y")
            except ValueError:
                continue
    return _current_month_tab(format_str)

def _load_x_activity_csv(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        logger.warning(f"X activity CSV not found at {csv_path}")
        return []
    rows = []
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row:
                    rows.append(row)
    except Exception as e:
        logger.error(f"Failed to read X activity CSV: {e}")
        return []
    return rows

def _ensure_activity_month_tab(spreadsheet, tab_name: str):
    try:
        return spreadsheet.worksheet(tab_name)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=23)
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
        worksheet.update("A1:I1", [x_headers])
        worksheet.update("M1:W1", [reddit_headers])
        return worksheet

def _sync_x_activity_csv_to_sheet(activity_spreadsheet, month_tab_format: str, csv_path: Path) -> int:
    rows = _load_x_activity_csv(csv_path)
    if not rows:
        return 0

    rows_by_tab: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        tab = _month_tab_from_date(row.get("date", ""), month_tab_format)
        rows_by_tab[tab].append(row)

    total_inserted = 0
    for tab_name, tab_rows in rows_by_tab.items():
        worksheet = _ensure_activity_month_tab(activity_spreadsheet, tab_name)

        try:
            existing_urls = set()
            url_col = worksheet.col_values(6)
            for url in url_col[1:]:
                url = url.strip() if url else ""
                if url:
                    existing_urls.add(url)
        except Exception as e:
            logger.warning(f"Failed to read existing URLs from {tab_name}: {e}")
            existing_urls = set()

        new_rows = []
        for row in tab_rows:
            activity_url = (row.get("activity_url") or "").strip()
            if not activity_url or activity_url in existing_urls:
                continue
            new_rows.append([
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

        if not new_rows:
            continue

        for start in range(0, len(new_rows), 500):
            batch = new_rows[start:start + 500]
            worksheet.append_rows(batch, value_input_option="RAW")
            total_inserted += len(batch)
        logger.info("Synced %s new X activities to %s", len(new_rows), tab_name)

    return total_inserted


def run_sync():
    """Run one sync cycle"""
    try:
        logger.info("=" * 60)
        logger.info(f"Starting sync cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        members_sheet_id = get_members_sheet_id()
        tasks_sheet_id = get_tasks_sheet_id()
        activity_sheet_id = get_activity_sheet_id()

        if not members_sheet_id or not tasks_sheet_id or not activity_sheet_id:
            logger.error("Missing sheet IDs in .env; sync cannot proceed")
            return

        credentials_file = CREDENTIALS_FILE
        if not credentials_file.exists():
            logger.error(f"Google credentials not found at {credentials_file}")
            return

        try:
            import gspread
        except Exception as e:
            logger.error(f"Missing gspread dependency: {e}")
            return

        from members_sheets_parser import MembersSheetsParser
        from members_service import MembersDBService

        config_file = dashboard_dir / "sync_config.json"
        month_tab_format = "MM/YY"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())
                month_tab_format = config.get("sync", {}).get("month_tab_format", month_tab_format)
            except Exception as e:
                logger.warning(f"Could not load month tab format: {e}")

        month_tab = _current_month_tab(month_tab_format)

        gc = gspread.service_account(filename=str(credentials_file))
        members_spreadsheet = gc.open_by_key(members_sheet_id)
        tasks_spreadsheet = gc.open_by_key(tasks_sheet_id)
        activity_spreadsheet = gc.open_by_key(activity_sheet_id)

        csv_activity_path = project_root / "database" / "x_activity_log.csv"
        csv_synced = _sync_x_activity_csv_to_sheet(
            activity_spreadsheet,
            month_tab_format,
            csv_activity_path,
        )
        if csv_synced:
            logger.info("Synced %s CSV X activities to activity sheet", csv_synced)

        parser = MembersSheetsParser()
        members_db = MembersDBService(str(project_root / "database" / "members.csv"))
        year_month = _month_tab_to_year_month(month_tab)

        members_rows = _fetch_sheet(members_spreadsheet, "Member Registry")
        members = parser.parse_members_registry(members_rows)
        members_synced = 0
        for member in members:
            if members_db.upsert_member(member):
                members_synced += 1

        tasks_rows = _fetch_sheet(tasks_spreadsheet, month_tab)
        tasks = parser.parse_monthly_content_tasks(tasks_rows, year_month)
        existing_tasks = {task.get("task_id"): task for task in members_db.get_tasks_for_month(year_month)}
        removed = members_db.delete_tasks_for_month(year_month)
        if removed:
            logger.info(f"Cleared {removed} tasks for {year_month} before sync")
        tasks_synced = 0
        for task in tasks:
            task_data = {
                'task_id': task.get('task_id'),
                'platform': task.get('platform'),
                'task_type': task.get('task_type'),
                'target_url': task.get('target_url'),
                'description': task.get('description'),
                'content': task.get('content'),
                'title': task.get('title'),
                'impressions': task.get('impressions', 0),
                'likes': task.get('likes', 0),
                'comments': task.get('comments', 0),
                'is_active': task.get('is_active', 1),
                'created_date': task.get('created_date'),
                'created_by': task.get('created_by'),
                'year_month': task.get('year_month'),
            }
            existing = existing_tasks.get(task_data.get("task_id"))
            if existing:
                if not task_data.get("content"):
                    task_data["content"] = existing.get("content")
                if not task_data.get("title"):
                    task_data["title"] = existing.get("title")
            if members_db.upsert_task(task_data):
                tasks_synced += 1

        try:
            from generate_titles import generate_missing_titles
            titles_csv = project_root / "database" / "coordinated_tasks.csv"
            titles_updated = generate_missing_titles(titles_csv)
            if titles_updated:
                logger.info("Generated %s missing titles", titles_updated)
        except Exception as e:
            logger.warning(f"Title generation skipped: {e}")

        x_rows = _fetch_sheet(activity_spreadsheet, month_tab, "A:I")
        x_activities = parser.parse_x_activity_log(x_rows)
        x_inserted = members_db.insert_x_activities_batch(x_activities)

        reddit_rows = _fetch_sheet(activity_spreadsheet, month_tab, "M:W")
        reddit_activities = parser.parse_reddit_activity_log(reddit_rows)
        reddit_inserted = members_db.insert_reddit_activities_batch(reddit_activities)

        logger.info(
            "Sync results: members=%s, tasks=%s, x_activities=%s, reddit_activities=%s",
            members_synced,
            tasks_synced,
            x_inserted,
            reddit_inserted,
        )
        logger.info("✅ Sync cycle completed successfully")

    except Exception as e:
        logger.error(f"❌ Sync cycle failed: {e}", exc_info=True)

def main():
    """Main sync worker loop"""
    logger.info("=" * 60)
    logger.info("Cybernetics Sync Worker Starting")
    logger.info("=" * 60)
    logger.info(f"Sync interval: {interval_minutes} minutes")
    logger.info(f"Sync enabled: {enabled}")

    if not enabled:
        logger.warning("Sync is disabled in config, worker will exit")
        return

    interval_seconds = interval_minutes * 60

    logger.info("Running initial sync...")
    run_sync()

    logger.info(f"Entering sync loop (every {interval_minutes} minutes)...")

    try:
        while True:
            time.sleep(interval_seconds)
            run_sync()

    except KeyboardInterrupt:
        logger.info("Sync worker interrupted, shutting down gracefully...")
    except Exception as e:
        logger.error(f"Sync worker crashed: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    main()
