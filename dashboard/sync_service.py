from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from logger_config import setup_logger
from links_service import LinksDBService
from sheets_parser import SheetsParser

logger = setup_logger(__name__)


class SyncService:
    def __init__(
        self,
        spreadsheet_id: str,
        sheets_service,
        template_creator,
        links_db: LinksDBService,
        stats_db=None,
        config: Optional[Dict] = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.sheets_service = sheets_service
        self.template_creator = template_creator
        self.links_db = links_db
        self.stats_db = stats_db
        self.config = config or {
            "sheet_template": {
                "x_columns": {},
                "reddit_columns": {},
                "summary_start_row": 1,
            }
        }
        self.parser = SheetsParser(self.config)

    def run(self, year_month: Optional[str] = None) -> None:
        sync_start_time = time.time()
        try:
            logger.info("=" * 80)
            logger.info("CYBERNETICS SYNC STARTED")
            logger.info("=" * 80)

            if not year_month:
                year_month = self._get_current_year_month()

            logger.info(f"Current month: {year_month}")

            logger.info("-" * 80)
            logger.info("PHASE 2: Sheet Validation")
            self._ensure_sheet_exists(year_month)

            logger.info("-" * 80)
            logger.info("PHASE 3: Reading data from Google Sheets")
            rows = self._fetch_sheet_data(year_month)
            logger.info(f"Fetched {len(rows)} rows from Sheets")

            x_summary = self.parser.parse_summary_x(rows)
            reddit_summary = self.parser.parse_summary_reddit(rows)

            posts = self.parser.parse_individual_posts(rows, year_month)
            overlap_year_month, overlap_posts = self._fetch_overlap_posts(year_month)

            logger.info("-" * 80)
            logger.info("PHASE 4: Calculating derived metrics")
            x_authors = self._count_authors(posts, "x")
            reddit_authors = self._count_authors(posts, "reddit")
            logger.info(f"X authors: {x_authors}")
            logger.info(f"Reddit authors: {reddit_authors}")

            logger.info("-" * 80)
            logger.info("PHASE 5: Saving aggregates to Stats DB")
            self._save_x_stats(year_month, x_summary, x_authors)
            self._save_reddit_stats(year_month, reddit_summary, reddit_authors)

            logger.info("-" * 80)
            logger.info("PHASE 6: Saving individual links to Links DB")
            inserted_count = self._save_links(posts, year_month)
            if overlap_posts and overlap_year_month:
                self._save_links(overlap_posts, overlap_year_month)
            logger.info(f"Inserted {inserted_count} links")

            logger.info("-" * 80)
            logger.info("PHASE 7: Finalization")
            sync_duration = time.time() - sync_start_time
            logger.info(f"✅ Sync completed successfully in {sync_duration:.2f} seconds")

            if sync_duration > 5:
                logger.warning(f"⚠️ Sync took {sync_duration:.2f}s (expected <5s)")

            logger.info("=" * 80)

        except Exception as e:
            sync_duration = time.time() - sync_start_time
            logger.error("=" * 80)
            logger.error(f"❌ SYNC FAILED after {sync_duration:.2f} seconds")
            logger.error(f"Error: {str(e)}")
            logger.error("=" * 80)
            logger.error("Full stack trace:", exc_info=True)
            raise

    def _get_current_year_month(self) -> str:
        now = datetime.now()
        year_month = now.strftime("%Y-%m")
        logger.debug(f"Current year-month: {year_month}")
        return year_month

    def _get_previous_year_month(self, year_month: str) -> str:
        year, month = year_month.split("-")
        month_num = int(month)
        year_num = int(year)
        if month_num == 1:
            return f"{year_num - 1}-12"
        return f"{year_num}-{month_num - 1:02d}"

    def _fetch_overlap_posts(self, year_month: str) -> tuple[str, List[Dict]]:
        try:
            previous_year_month = self._get_previous_year_month(year_month)
            prev_rows = self._fetch_sheet_data(previous_year_month)
            prev_posts = self.parser.parse_individual_posts(prev_rows, previous_year_month)
            cutoff_date = datetime.strptime(f"{year_month}-01", "%Y-%m-%d").date() - timedelta(days=10)

            overlap_posts = []
            for post in prev_posts:
                date_str = post.get("date")
                if not date_str:
                    continue
                try:
                    post_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if post_date >= cutoff_date:
                    overlap_posts.append(post)

            if overlap_posts:
                logger.info(
                    f"Including {len(overlap_posts)} posts from {previous_year_month} "
                    f"(since {cutoff_date.isoformat()})"
                )
            return previous_year_month, overlap_posts
        except Exception as e:
            logger.warning(f"Overlap fetch skipped: {str(e)}")
            return "", []

    def _ensure_sheet_exists(self, year_month: str) -> None:
        logger.info(f"Checking if sheet exists for {year_month}")

        sheet_created = self.template_creator.ensure_month_sheet_exists(year_month)

        if sheet_created:
            logger.info("✅ Sheet validation complete")
        else:
            logger.error("❌ Sheet validation failed")
            raise Exception("Failed to ensure sheet exists")

    def _fetch_sheet_data(self, year_month: str) -> List[List[str]]:
        year, month = year_month.split("-")
        year_short = year[-2:]
        sheet_name = f"{month}/{year_short}"

        logger.info(f"Fetching data from sheet: {sheet_name}")

        try:
            range_name = f"'{sheet_name}'!A:P"
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()

            rows = result.get("values", [])
            logger.info(f"✅ Fetched {len(rows)} rows from Sheets")
            return rows

        except Exception as e:
            logger.error(f"❌ Error fetching sheet data: {str(e)}", exc_info=True)
            raise

    def _count_authors(self, posts: List[Dict], platform: str) -> int:
        authors = set()
        for post in posts:
            if post["platform"] == platform and post.get("author"):
                authors.add(post["author"])

        count = len(authors)
        logger.debug(f"Counted {count} unique authors for {platform}")
        return count

    def _save_x_stats(self, year_month: str, summary: Dict[str, int], authors_count: int) -> None:
        stats_data = {
            "year_month": year_month,
            "platform": "x",
            "total_impressions": summary.get("total_impressions", 0),
            "total_likes": summary.get("total_likes", 0),
            "total_posts": summary.get("total_posts", 0),
            "unique_authors": authors_count,
        }
        logger.debug(f"X stats data: {stats_data}")

        if not self.stats_db:
            logger.warning("Stats DB not configured; skipping X stats save")
            return

        success = self.stats_db.upsert_monthly_stats(stats_data)

        if success:
            logger.info("✅ X stats saved successfully")
        else:
            logger.error("❌ Failed to save X stats")
            raise Exception("Failed to save X stats")

    def _save_reddit_stats(self, year_month: str, summary: Dict[str, int], authors_count: int) -> None:
        stats_data = {
            "year_month": year_month,
            "platform": "reddit",
            "total_views": summary.get("total_views", 0),
            "total_upvotes": summary.get("total_upvotes", 0),
            "total_posts": summary.get("total_posts", 0),
            "unique_authors": authors_count,
        }

        logger.debug(f"Reddit stats data: {stats_data}")

        if not self.stats_db:
            logger.warning("Stats DB not configured; skipping Reddit stats save")
            return

        success = self.stats_db.upsert_monthly_stats(stats_data)

        if success:
            logger.info("✅ Reddit stats saved successfully")
        else:
            logger.error("❌ Failed to save Reddit stats")
            raise Exception("Failed to save Reddit stats")

    def _save_links(self, posts: List[Dict], year_month: str) -> int:
        logger.info(f"Saving {len(posts)} posts to Links DB")

        inserted_count = self.links_db.insert_links_batch(posts, year_month)

        logger.info(f"✅ Saved {inserted_count}/{len(posts)} links")
        return inserted_count
