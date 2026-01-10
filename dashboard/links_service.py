from datetime import datetime
from typing import List, Dict, Optional
import re
from pathlib import Path
from logger_config import setup_logger
from csv_store import load_csv, merge_fieldnames, write_csv, locked_csv

logger = setup_logger(__name__)

DEFAULT_LINK_FIELDS = [
    "id",
    "year_month",
    "date",
    "platform",
    "author",
    "url",
    "impressions_or_views",
    "likes",
    "comments",
    "retweets",
    "notes",
    "synced_at",
]


class LinksDBService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if not Path(db_path).exists():
            logger.warning(f"Links CSV not found at {db_path}, it will be created on write")

    def _read_links(self) -> tuple[List[str], List[Dict[str, str]]]:
        fields, rows = load_csv(self.db_path)
        if not fields:
            fields = list(DEFAULT_LINK_FIELDS)
        return fields, rows

    def _write_links(self, fields: List[str], rows: List[Dict[str, str]]) -> None:
        write_csv(self.db_path, fields, rows)

    def _next_id(self, rows: List[Dict[str, str]]) -> int:
        max_id = 0
        for row in rows:
            try:
                value = int(row.get("id", 0))
            except ValueError:
                value = 0
            max_id = max(max_id, value)
        return max_id + 1

    def _parse_metric(self, value) -> int:
        if value is None:
            return 0
        text = str(value).strip().replace(",", "")
        if not text:
            return 0
        multiplier = 1
        suffix = text[-1].upper()
        if suffix in {"K", "M", "B"}:
            multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
            text = text[:-1].strip()
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0

    def _normalize_x_url(self, url: str) -> Optional[str]:
        if not url:
            return None
        if url.isdigit():
            return f"https://x.com/i/status/{url}"
        match = re.search(r"/status(?:es)?/(\d+)", url)
        if match:
            return f"https://x.com/i/status/{match.group(1)}"
        return None

    def get_links_for_month(self, year_month: str) -> List[Dict]:
        try:
            _, rows = self._read_links()
            filtered = [row for row in rows if row.get("year_month") == year_month]
            filtered.sort(key=lambda r: r.get("date", ""), reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error querying links: {str(e)}", exc_info=True)
            return []

    def get_links_for_month_and_platform(self, year_month: str, platform: str) -> List[Dict]:
        try:
            _, rows = self._read_links()
            filtered = [
                row for row in rows
                if row.get("year_month") == year_month and row.get("platform") == platform
            ]
            filtered.sort(key=lambda r: r.get("date", ""), reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error querying links: {str(e)}", exc_info=True)
            return []

    def get_links_by_author(self, year_month: str, author: str) -> List[Dict]:
        try:
            _, rows = self._read_links()
            filtered = [
                row for row in rows
                if row.get("year_month") == year_month and row.get("author") == author
            ]
            filtered.sort(key=lambda r: r.get("date", ""), reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error querying links: {str(e)}", exc_info=True)
            return []

    def insert_link(self, link_data: Dict) -> bool:
        if "year_month" not in link_data:
            logger.error("Cannot insert link without year_month")
            return False

        try:
            with locked_csv(self.db_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_LINK_FIELDS)
                fields = merge_fieldnames(fields, link_data.keys())

                url = link_data.get("url")
                if link_data.get("platform") == "x":
                    url = self._normalize_x_url(url)
                    if not url:
                        logger.warning("Skipping X link without status ID")
                        return False

                likes_value = link_data.get("likes", 0)
                if link_data.get("platform") == "reddit":
                    likes_value = link_data.get("upvotes", likes_value)

                new_id = self._next_id(rows)
                synced_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                row = {
                    "id": new_id,
                    "year_month": link_data["year_month"],
                    "date": link_data.get("date"),
                    "platform": link_data["platform"],
                    "author": link_data.get("author", "Unknown"),
                    "url": url,
                    "impressions_or_views": link_data.get("impressions_or_views", 0),
                    "likes": likes_value,
                    "comments": link_data.get("comments", 0),
                    "retweets": link_data.get("retweets", 0),
                    "notes": link_data.get("notes", ""),
                    "synced_at": link_data.get("synced_at", synced_at),
                }

                rows.append(row)
                write(fields, rows)
                return True
        except Exception as e:
            logger.error(f"Error inserting link: {str(e)}", exc_info=True)
            return False

    def insert_links_batch(self, links: List[Dict], year_month: str) -> int:
        inserted_count = 0

        try:
            with locked_csv(self.db_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_LINK_FIELDS)
                next_id = self._next_id(rows)
                synced_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                for link_data in links:
                    try:
                        url = link_data.get("url")
                        if link_data.get("platform") == "x":
                            url = self._normalize_x_url(url)
                            if not url:
                                logger.warning("Skipping X link without status ID")
                                continue

                        likes_value = link_data.get("likes", 0)
                        if link_data.get("platform") == "reddit":
                            likes_value = link_data.get("upvotes", likes_value)

                        row = {
                            "id": next_id,
                            "year_month": year_month,
                            "date": link_data.get("date"),
                            "platform": link_data["platform"],
                            "author": link_data.get("author", "Unknown"),
                            "url": url,
                            "impressions_or_views": link_data.get("impressions_or_views", 0),
                            "likes": likes_value,
                            "comments": link_data.get("comments", 0),
                            "retweets": link_data.get("retweets", 0),
                            "notes": link_data.get("notes", ""),
                            "synced_at": link_data.get("synced_at", synced_at),
                        }
                        fields = merge_fieldnames(fields, row.keys())
                        rows.append(row)
                        inserted_count += 1
                        next_id += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert link: {str(e)}")
                        continue

                if inserted_count:
                    write(fields, rows)

                return inserted_count
        except Exception as e:
            logger.error(f"Error in batch insert: {str(e)}", exc_info=True)
            return inserted_count

    def get_posts_with_details(self, year_month: str, platform: str) -> List[Dict]:
        """Get all individual posts with detailed metrics for a given month and platform."""
        try:
            _, rows = self._read_links()
            filtered = [
                row for row in rows
                if row.get("year_month") == year_month and row.get("platform") == platform
            ]
            filtered.sort(key=lambda r: self._parse_metric(r.get("impressions_or_views")), reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error querying posts with details: {str(e)}", exc_info=True)
            return []
