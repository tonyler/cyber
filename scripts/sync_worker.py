#!/usr/bin/env python3
"""
Sync Worker - Periodically syncs data from Google Sheets to local database
"""

import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime

# Add paths
project_root = Path(__file__).parent.parent
dashboard_dir = project_root / "dashboard"
sys.path.insert(0, str(dashboard_dir))

from logger_config import setup_logger

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

def _load_env_value(env_path: Path, key: str) -> str:
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


def run_sync():
    """Run one sync cycle"""
    try:
        logger.info("=" * 60)
        logger.info(f"Starting sync cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        env_path = dashboard_dir / ".env"
        members_sheet_id = os.getenv("MEMBERS_SHEET_ID") or _load_env_value(env_path, "MEMBERS_SHEET_ID")
        tasks_sheet_id = os.getenv("TASKS_SHEET_ID") or _load_env_value(env_path, "TASKS_SHEET_ID")
        activity_sheet_id = os.getenv("ACTIVITY_SHEET_ID") or _load_env_value(env_path, "ACTIVITY_SHEET_ID")
        if not activity_sheet_id:
            activity_sheet_id = os.getenv("SPREADSHEET_ID") or _load_env_value(env_path, "SPREADSHEET_ID")

        if not members_sheet_id or not tasks_sheet_id or not activity_sheet_id:
            logger.error("Missing sheet IDs; sync cannot proceed")
            return

        credentials_file = project_root / "shared" / "credentials" / "google.json"
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

        parser = MembersSheetsParser()
        members_db = MembersDBService(str(project_root / "database" / "members.csv"))
        year_month = _month_tab_to_year_month(month_tab)

        members_rows = _fetch_sheet(members_spreadsheet, "Member Registry")
        members = parser.parse_members_registry(members_rows)
        members_synced = 0
        for member in members:
            if members_db.upsert_member(member):
                members_synced += 1

        tasks_rows = _fetch_sheet(tasks_spreadsheet, month_tab, "A:P")
        tasks = parser.parse_monthly_content_tasks(tasks_rows, year_month)
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
                'impressions': task.get('impressions', 0),
                'likes': task.get('likes', 0),
                'comments': task.get('comments', 0),
                'is_active': task.get('is_active', 1),
                'created_date': task.get('created_date'),
                'created_by': task.get('created_by'),
                'year_month': task.get('year_month'),
            }
            if members_db.upsert_task(task_data):
                tasks_synced += 1

        x_rows = _fetch_sheet(activity_spreadsheet, month_tab, "A:K")
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
