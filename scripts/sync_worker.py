#!/usr/bin/env python3
"""
Sync Worker - Data flow management between local CSVs and Google Sheets.

DATA FLOW DIRECTION:
====================
┌─────────────────────────────────────────────────────────────────┐
│  MEMBERS:     Discord Bot → Google Sheets → Local CSV           │
│               (Sheets = source of truth, CSV = local cache)     │
│                                                                 │
│  ACTIVITIES:  X Scraper → Local CSV → Google Sheets             │
│               (CSV = source of truth, Sheets = backup)          │
│                                                                 │
│  LINKS:       X Scraper → Local CSV → Google Sheets             │
│               (CSV = source of truth, Sheets = backup)          │
└─────────────────────────────────────────────────────────────────┘
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


def _get_sheet_data_as_dict(worksheet, key_column: int) -> dict:
    """Get all sheet rows as dict keyed by specified column index."""
    try:
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            return {}
        result = {}
        for row_idx, row in enumerate(all_values[1:], start=2):
            if row and len(row) > key_column:
                key = row[key_column]
                if key:
                    result[key] = {'row_idx': row_idx, 'data': row}
        return result
    except Exception as e:
        logger.warning(f"Could not read sheet data: {e}")
        return {}


# ============================================================
# MEMBERS: Google Sheets → Local CSV
# (Discord bot writes to Sheets, sync pulls to local CSV cache)
# ============================================================

def download_members_from_sheets(gc, members_sheet_id: str) -> int:
    """Download members FROM Google Sheets TO local CSV.

    Direction: Sheets → CSV
    Reason: Discord bot writes directly to Sheets (source of truth)
    """
    csv_path = project_root / "database" / "members.csv"

    headers = ['discord_user', 'x_handle', 'reddit_username', 'status',
               'joined_date', 'last_activity', 'total_points', 'last_active',
               'total_tasks', 'x_profile_url', 'reddit_profile_url', 'registration_date']

    try:
        spreadsheet = gc.open_by_key(members_sheet_id)

        try:
            worksheet = spreadsheet.worksheet("Member Registry")
        except Exception:
            logger.warning("Member Registry worksheet not found")
            return 0

        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            logger.info("No members in sheet")
            return 0

        rows = []
        for row in all_values[1:]:
            if not row or not row[0]:
                continue
            while len(row) < len(headers):
                row.append('')
            rows.append({
                'discord_user': row[0],
                'x_handle': row[1],
                'reddit_username': row[2],
                'status': row[3],
                'joined_date': row[4],
                'last_activity': row[5],
                'total_points': row[6],
                'last_active': row[7],
                'total_tasks': row[8],
                'x_profile_url': row[9],
                'reddit_profile_url': row[10],
                'registration_date': row[11] if len(row) > 11 else '',
            })

        if _write_csv(csv_path, rows, headers):
            logger.info(f"[Sheets→CSV] Downloaded {len(rows)} members to local cache")
            return len(rows)
        return 0

    except Exception as e:
        logger.error(f"Failed to download members: {e}")
        return 0


# ============================================================
# LINKS: Local CSV → Google Sheets (backup)
# (Scraper writes to CSV, sync backs up to Sheets)
# ============================================================

def backup_links_to_sheets(gc, tasks_sheet_id: str) -> int:
    """Backup links FROM local CSV TO Google Sheets.

    Direction: CSV → Sheets
    Reason: Scraper writes to CSV (source of truth), Sheets is backup
    """
    csv_path = project_root / "database" / "links.csv"
    rows = _read_csv(csv_path)

    if not rows:
        return 0

    year_month = _current_year_month()
    month_rows = [r for r in rows if r.get('year_month') == year_month]

    if not month_rows:
        return 0

    headers = ['id', 'platform', 'url', 'author', 'year_month', 'date',
               'impressions', 'likes', 'comments', 'retweets', 'content', 'title', 'synced_at']

    try:
        spreadsheet = gc.open_by_key(tasks_sheet_id)
        tab_name = _current_month_tab()

        try:
            worksheet = spreadsheet.worksheet(tab_name)
        except Exception:
            worksheet = spreadsheet.add_worksheet(title=tab_name, rows=500, cols=len(headers))
            worksheet.update(values=[headers], range_name='A1')

        existing_data = worksheet.get_all_values()
        if not existing_data:
            worksheet.update(values=[headers], range_name='A1')

        existing = _get_sheet_data_as_dict(worksheet, key_column=0)

        updates = []
        appends = []

        for r in month_rows:
            link_id = r.get('id', '')
            if not link_id:
                continue

            row_data = [
                link_id,
                r.get('platform', ''),
                r.get('url', ''),
                r.get('author', ''),
                r.get('year_month', ''),
                r.get('date', ''),
                r.get('impressions', ''),
                r.get('likes', ''),
                r.get('comments', ''),
                r.get('retweets', ''),
                (r.get('content', '') or '')[:1000],
                r.get('title', ''),
                r.get('synced_at', ''),
            ]

            if link_id in existing:
                row_idx = existing[link_id]['row_idx']
                updates.append({'range': f'A{row_idx}:M{row_idx}', 'values': [row_data]})
            else:
                appends.append(row_data)

        if updates:
            worksheet.batch_update(updates, value_input_option='RAW')

        if appends:
            worksheet.append_rows(appends, value_input_option='RAW')

        logger.info(f"[CSV→Sheets] Backed up links to {tab_name}: {len(updates)} updated, {len(appends)} added")
        return len(updates) + len(appends)

    except Exception as e:
        logger.error(f"Failed to backup links: {e}")
        return 0


# ============================================================
# ACTIVITIES: Local CSV → Google Sheets (backup)
# (Scraper writes to CSV, sync backs up to Sheets)
# ============================================================

def backup_activities_to_sheets(gc, activity_sheet_id: str) -> int:
    """Backup activities FROM local CSV TO Google Sheets.

    Direction: CSV → Sheets
    Reason: Scraper writes to CSV (source of truth), Sheets is backup
    """
    csv_path = project_root / "database" / "x_activity_log.csv"
    rows = _read_csv(csv_path)

    if not rows:
        return 0

    headers = ['date', 'time', 'discord_user', 'x_handle', 'activity_type',
               'activity_url', 'target_url', 'task_id', 'notes']

    rows_by_month = defaultdict(list)
    for r in rows:
        date_str = r.get('date', '')
        if date_str and len(date_str) >= 7:
            ym = date_str[:7]
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
            try:
                worksheet = spreadsheet.worksheet(tab_name)
            except Exception:
                worksheet = spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=len(headers))
                worksheet.update(values=[headers], range_name='A1')

            existing_data = worksheet.get_all_values()
            if not existing_data:
                worksheet.update(values=[headers], range_name='A1')

            existing = _get_sheet_data_as_dict(worksheet, key_column=5)

            updates = []
            appends = []

            for r in tab_rows:
                activity_url = r.get('activity_url', '')
                if not activity_url:
                    continue

                row_data = [
                    r.get('date', ''),
                    r.get('time', ''),
                    r.get('discord_user', ''),
                    r.get('x_handle', ''),
                    r.get('activity_type', ''),
                    activity_url,
                    r.get('target_url', ''),
                    r.get('task_id', ''),
                    r.get('notes', ''),
                ]

                if activity_url in existing:
                    row_idx = existing[activity_url]['row_idx']
                    updates.append({'range': f'A{row_idx}:I{row_idx}', 'values': [row_data]})
                else:
                    appends.append(row_data)

            if updates:
                for start in range(0, len(updates), 500):
                    batch = updates[start:start + 500]
                    worksheet.batch_update(batch, value_input_option='RAW')

            if appends:
                worksheet.append_rows(appends, value_input_option='RAW')

            logger.info(f"[CSV→Sheets] Backed up activities to {tab_name}: {len(updates)} updated, {len(appends)} added")
            total_synced += len(updates) + len(appends)

        except Exception as e:
            logger.warning(f"Failed to backup activities to {tab_name}: {e}")

    return total_synced


# ============================================================
# MAIN SYNC
# ============================================================

def run_sync():
    """Run one sync cycle."""
    logger.info("=" * 60)
    logger.info(f"Sync started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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

    # 1. Members: Download FROM Sheets TO local CSV (Sheets = source of truth)
    members_count = download_members_from_sheets(gc, members_sheet_id)

    # 2. Links: Backup FROM local CSV TO Sheets (CSV = source of truth)
    links_count = backup_links_to_sheets(gc, tasks_sheet_id)

    # 3. Activities: Backup FROM local CSV TO Sheets (CSV = source of truth)
    activities_count = backup_activities_to_sheets(gc, activity_sheet_id)

    logger.info(f"Sync results: members_downloaded={members_count}, links_backed_up={links_count}, activities_backed_up={activities_count}")
    logger.info("✅ Sync completed")


def main():
    logger.info("=" * 60)
    logger.info("Cybernetics Sync Worker")
    logger.info("=" * 60)
    logger.info(f"Interval: {interval_minutes} minutes")
    logger.info("")
    logger.info("Data flow:")
    logger.info("  MEMBERS:    Sheets → CSV  (Sheets is source of truth)")
    logger.info("  LINKS:      CSV → Sheets  (CSV is source of truth)")
    logger.info("  ACTIVITIES: CSV → Sheets  (CSV is source of truth)")
    logger.info("")

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
