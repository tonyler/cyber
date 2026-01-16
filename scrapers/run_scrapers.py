#!/usr/bin/env python3
import sys
import json
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
scrapers_dir = project_root / "scrapers"
shared_dir = project_root / "shared"
sys.path.insert(0, str(scrapers_dir))
sys.path.insert(0, str(shared_dir))

from logger_config import setup_logger
from x_scraper import XScraper
from reddit_scraper import RedditScraper

logger = setup_logger(__name__)

MEMBERS_DB_PATH = str(project_root / "database" / "members.csv")
LINKS_DB_PATH = str(project_root / "database" / "links.csv")
CREDENTIALS_FILE = str(project_root / "shared" / "credentials" / "google.json")
SYNC_CONFIG_FILE = project_root / "shared" / "config" / "sync_config.json"
ENV_FILE = project_root / ".env"


def load_dashboard_env() -> dict:
    config = {}
    if not ENV_FILE.exists():
        return config
    with ENV_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


def load_sync_config() -> dict:
    if not SYNC_CONFIG_FILE.exists():
        return {}
    with SYNC_CONFIG_FILE.open("r") as f:
        return json.load(f)

def run_x_scraper(headless: bool = True, limit: int = None, verbose_metrics: bool = False):
    logger.info("=" * 80)
    logger.info("STARTING X/TWITTER SCRAPER")
    logger.info("=" * 80)

    try:
        env_config = load_dashboard_env()
        sync_config = load_sync_config()

        # Get sheet IDs from .env
        tasks_sheet_id = env_config.get("TASKS_SHEET_ID")  # For reading URLs and writing metrics
        activity_sheet_id = env_config.get("ACTIVITY_SHEET_ID")  # For writing member activities

        with XScraper(
            members_db_path=MEMBERS_DB_PATH,
            links_db_path=LINKS_DB_PATH,
            activity_sheet_id=activity_sheet_id,
            credentials_file=CREDENTIALS_FILE,
            headless=headless,
            stats_sheet_id=tasks_sheet_id,
            sheet_config=sync_config,
            verbose_metrics=verbose_metrics
        ) as scraper:
            scraper.run(limit=limit)

        logger.info("✅ X scraper completed successfully")

    except Exception as e:
        logger.error(f"❌ X scraper failed: {str(e)}", exc_info=True)
        raise

def run_reddit_scraper(headless: bool = True, limit: int = None, verbose_metrics: bool = False):
    logger.info("=" * 80)
    logger.info("STARTING REDDIT SCRAPER")
    logger.info("=" * 80)

    try:
        env_config = load_dashboard_env()
        sync_config = load_sync_config()

        # Get sheet IDs from .env
        tasks_sheet_id = env_config.get("TASKS_SHEET_ID")  # For reading URLs and writing metrics
        activity_sheet_id = env_config.get("ACTIVITY_SHEET_ID")  # For writing member activities

        with RedditScraper(
            members_db_path=MEMBERS_DB_PATH,
            links_db_path=LINKS_DB_PATH,
            activity_sheet_id=activity_sheet_id,
            credentials_file=CREDENTIALS_FILE,
            headless=headless,
            stats_sheet_id=tasks_sheet_id,
            sheet_config=sync_config,
            verbose_metrics=verbose_metrics
        ) as scraper:
            scraper.run(limit=limit)

        logger.info("✅ Reddit scraper completed successfully")

    except Exception as e:
        logger.error(f"❌ Reddit scraper failed: {str(e)}", exc_info=True)
        raise

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--x', action='store_true', help='Run X scraper')
    parser.add_argument('--reddit', action='store_true', help='Run Reddit scraper')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of links')
    parser.add_argument('--no-headless', dest='headless', action='store_false')
    parser.add_argument('--verbose-metrics', action='store_true',
                        help='Log detailed metrics extraction for each URL')
    parser.set_defaults(headless=True)

    args = parser.parse_args()

    run_x = args.x
    run_reddit = args.reddit
    if not run_x and not run_reddit:
        run_x = True
        run_reddit = True

    if run_x:
        run_x_scraper(headless=args.headless, limit=args.limit, verbose_metrics=args.verbose_metrics)

    if run_reddit:
        run_reddit_scraper(headless=args.headless, limit=args.limit, verbose_metrics=args.verbose_metrics)

if __name__ == '__main__':
    main()
