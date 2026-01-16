#!/usr/bin/env python3
"""
Sync Worker - Simple one-way syncs:
- Members: Google Sheets → local CSV (members register via sheets/bot)
- Links/Posts: local CSV → Google Sheets (scraper is source of truth)
- Activities: local CSV → Google Sheets (scraper writes activities)
"""

import sys
import time
import json
import csv
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

# Add paths
project_root = Path(__file__).resolve().parent.parent
shared_dir = project_root / "shared"
sys.path.insert(0, str(shared_dir))

from config import (
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
config_file = shared_dir / "config" / "sync_config.json"
try:
    with open(config_file) as f:
        config = json.load(f)
    sync_config = config.get('sync', {})
    interval_minutes = sync_config.get('interval_minutes', 30)
    enabled = sync_config.get('enabled', True)
    month_tab_format = sync_config.get('month_tab_format', 'MM/YY')
except Exception as e:
    logger.warning(f"Could not load sync config: {e}, using defaults")
    interval_minutes = 30
    enabled = True
    month_tab_format = 'MM/YY'


def _current_month_tab() -> str:
    now = datetime.now(timezone.utc)
    if month_tab_format == "MM/YYYY":
        return now.strftime("%m/%Y")
    return now.strftime("%m/%y")


def _current_year_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open('r', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Failed to read {path}: {e}")
        return []


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    try:
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        return True
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")
        return False


# ============================================================
# MEMBERS: Local → Sheets
# ============================================================

def sync_members_to_sheets(gc, members_sheet_id: str) -> int:
    """Upload members.csv to Google Sheets - exact CSV mirror."""
    csv_path = project_root / "database" / "members.csv"
    rows = _read_csv(csv_path)

    if not rows:
        logger.info("No members to sync")
        return 0

    # CSV headers - exact match
    headers = ['discord_user', 'x_handle', 'reddit_username', 'status',
               'joined_date', 'last_activity', 'total_points', 'last_active',
               'total_tasks', 'x_profile_url', 'reddit_profile_url', 'registration_date']

    try:
        spreadsheet = gc.open_by_key(members_sheet_id)

        # Get or create worksheet
        try:
            worksheet = spreadsheet.worksheet("Member Registry")
        except Exception:
            worksheet = spreadsheet.add_worksheet(title="Member Registry", rows=500, cols=len(headers))

        # Clear and rewrite with exact CSV format
        worksheet.clear()
        worksheet.update(values=[headers], range_name='A1')

        # Prepare all rows matching CSV exactly
        sheet_rows = []
        for r in rows:
            sheet_rows.append([
                r.get('discord_user', ''),
                r.get('x_handle', ''),
                r.get('reddit_username', ''),
                r.get('status', ''),
                r.get('joined_date', ''),
                r.get('last_activity', ''),
                r.get('total_points', ''),
                r.get('last_active', ''),
                r.get('total_tasks', ''),
                r.get('x_profile_url', ''),
                r.get('reddit_profile_url', ''),
                r.get('registration_date', ''),
            ])

        if sheet_rows:
            worksheet.update(values=sheet_rows, range_name=f'A2:L{len(sheet_rows)+1}', value_input_option='RAW')
            logger.info(f"Synced {len(sheet_rows)} members to Member Registry (full refresh)")

        return len(sheet_rows)

    except Exception as e:
        logger.error(f"Failed to sync members to sheets: {e}")
        return 0


# ============================================================
# LINKS: Local → Sheets
# ============================================================

def sync_links_to_sheets(gc, tasks_sheet_id: str) -> int:
    """Upload links.csv to Google Sheets - exact CSV mirror."""
    csv_path = project_root / "database" / "links.csv"
    rows = _read_csv(csv_path)

    if not rows:
        logger.info("No links to sync")
        return 0

    # Filter to current month
    year_month = _current_year_month()
    month_rows = [r for r in rows if r.get('year_month') == year_month]

    if not month_rows:
        logger.info(f"No links for {year_month}")
        return 0

    # CSV headers - exact match
    headers = ['id', 'platform', 'url', 'author', 'year_month', 'date',
               'impressions', 'likes', 'comments', 'retweets', 'content', 'title', 'synced_at']

    try:
        spreadsheet = gc.open_by_key(tasks_sheet_id)
        tab_name = _current_month_tab()

        # Get or create worksheet
        try:
            worksheet = spreadsheet.worksheet(tab_name)
        except Exception:
            worksheet = spreadsheet.add_worksheet(title=tab_name, rows=500, cols=len(headers))

        # Clear and rewrite with exact CSV format
        worksheet.clear()
        worksheet.update(values=[headers], range_name='A1')

        # Prepare all rows matching CSV exactly
        sheet_rows = []
        for r in month_rows:
            sheet_rows.append([
                r.get('id', ''),
                r.get('platform', ''),
                r.get('url', ''),
                r.get('author', ''),
                r.get('year_month', ''),
                r.get('date', ''),
                r.get('impressions', ''),
                r.get('likes', ''),
                r.get('comments', ''),
                r.get('retweets', ''),
                (r.get('content', '') or '')[:1000],  # Truncate for sheets
                r.get('title', ''),
                r.get('synced_at', ''),
            ])

        if sheet_rows:
            worksheet.update(values=sheet_rows, range_name=f'A2:M{len(sheet_rows)+1}', value_input_option='RAW')
            logger.info(f"Synced {len(sheet_rows)} links to {tab_name} (full refresh)")

        return len(sheet_rows)

    except Exception as e:
        logger.error(f"Failed to sync links to sheets: {e}")
        return 0


# ============================================================
# ACTIVITIES: Local → Sheets
# ============================================================

def sync_activities_to_sheets(gc, activity_sheet_id: str) -> int:
    """Upload x_activity_log.csv to Google Sheets - exact CSV mirror."""
    csv_path = project_root / "database" / "x_activity_log.csv"
    rows = _read_csv(csv_path)

    if not rows:
        return 0

    # CSV headers - exact match
    headers = ['date', 'time', 'discord_user', 'x_handle', 'activity_type',
               'activity_url', 'target_url', 'task_id', 'notes']

    # Group by month
    rows_by_month = defaultdict(list)
    for r in rows:
        date_str = r.get('date', '')
        if date_str and len(date_str) >= 7:
            ym = date_str[:7]  # YYYY-MM
            try:
                dt = datetime.strptime(ym, "%Y-%m")
                if month_tab_format == "MM/YYYY":
                    tab = dt.strftime("%m/%Y")
                else:
                    tab = dt.strftime("%m/%y")
                rows_by_month[tab].append(r)
            except Exception:
                pass

    if not rows_by_month:
        return 0

    try:
        spreadsheet = gc.open_by_key(activity_sheet_id)
    except Exception as e:
        logger.error(f"Failed to open activity sheet: {e}")
        return 0

    total_synced = 0

    for tab_name, tab_rows in rows_by_month.items():
        try:
            # Get or create worksheet
            try:
                worksheet = spreadsheet.worksheet(tab_name)
            except Exception:
                worksheet = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=len(headers))

            # Clear and rewrite with exact CSV format
            worksheet.clear()
            worksheet.update(values=[headers], range_name='A1')

            # Prepare all rows matching CSV exactly
            sheet_rows = []
            for r in tab_rows:
                sheet_rows.append([
                    r.get('date', ''),
                    r.get('time', ''),
                    r.get('discord_user', ''),
                    r.get('x_handle', ''),
                    r.get('activity_type', ''),
                    r.get('activity_url', ''),
                    r.get('target_url', ''),
                    r.get('task_id', ''),
                    r.get('notes', ''),
                ])

            if sheet_rows:
                # Batch update
                for start in range(0, len(sheet_rows), 500):
                    batch = sheet_rows[start:start + 500]
                    end_row = start + len(batch) + 1
                    worksheet.update(values=batch, range_name=f'A{start+2}:I{end_row}', value_input_option='RAW')
                logger.info(f"Synced {len(sheet_rows)} activities to {tab_name} (full refresh)")
                total_synced += len(sheet_rows)

        except Exception as e:
            logger.warning(f"Failed to sync activities to {tab_name}: {e}")

    return total_synced


# ============================================================
# MAIN SYNC
# ============================================================

def run_sync():
    """Run one sync cycle."""
    logger.info("=" * 60)
    logger.info(f"Starting sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    members_sheet_id = get_members_sheet_id()
    tasks_sheet_id = get_tasks_sheet_id()
    activity_sheet_id = get_activity_sheet_id()

    if not all([members_sheet_id, tasks_sheet_id, activity_sheet_id]):
        logger.error("Missing sheet IDs in .env")
        return

    if not CREDENTIALS_FILE.exists():
        logger.error(f"Google credentials not found: {CREDENTIALS_FILE}")
        return

    try:
        import gspread
        gc = gspread.service_account(filename=str(CREDENTIALS_FILE))
    except Exception as e:
        logger.error(f"Failed to authenticate with Google: {e}")
        return

    # 1. Members: Local → Sheets
    members_synced = sync_members_to_sheets(gc, members_sheet_id)

    # 2. Links: Local → Sheets
    links_synced = sync_links_to_sheets(gc, tasks_sheet_id)

    # 3. Activities: Local → Sheets
    activities_synced = sync_activities_to_sheets(gc, activity_sheet_id)

    logger.info(f"Sync results: members={members_synced}, links={links_synced}, activities={activities_synced}")
    logger.info("✅ Sync completed")


def main():
    logger.info("=" * 60)
    logger.info("Cybernetics Sync Worker (Minimal)")
    logger.info("=" * 60)
    logger.info(f"Interval: {interval_minutes} minutes")

    if not enabled:
        logger.warning("Sync disabled in config")
        return

    logger.info("Running initial sync...")
    run_sync()

    logger.info(f"Entering sync loop (every {interval_minutes} min)...")

    try:
        while True:
            time.sleep(interval_minutes * 60)
            run_sync()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == '__main__':
    main()
