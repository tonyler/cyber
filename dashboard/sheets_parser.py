from typing import Dict, List, Optional
from datetime import datetime
import re
from logger_config import setup_logger

logger = setup_logger(__name__)

class SheetsParser:
    def __init__(self, config: dict):
        self.config = config
        self.x_columns = config['sheet_template']['x_columns']
        self.reddit_columns = config['sheet_template']['reddit_columns']
        self.summary_start_row = config['sheet_template']['summary_start_row']
        logger.info("SheetsParser initialized")
        logger.debug(f"X columns: {self.x_columns}")
        logger.debug(f"Reddit columns: {self.reddit_columns}")
        logger.debug(f"Summary start row: {self.summary_start_row}")

    def parse_summary_x(self, rows: List[List[str]]) -> Dict[str, int]:
        logger.info("Parsing X summary statistics")

        summary = {
            'total_impressions': 0,
            'total_likes': 0,
            'total_posts': 0
        }

        try:
            for i, row in enumerate(rows):
                if i == 0:
                    continue

                if len(row) > 7:
                    label_h = row[7].strip() if row[7] else ""

                    if "Total Impressions" in label_h or "Total Likes" in label_h or "Total Posts" in label_h:
                        if i + 1 < len(rows) and len(rows[i + 1]) > 7:
                            value_str = rows[i + 1][7].strip() if rows[i + 1][7] else "0"

                            if "Total Impressions" in label_h:
                                summary['total_impressions'] = self._parse_int(value_str)
                                logger.debug(f"Found X Total Impressions: {summary['total_impressions']}")
                            elif "Total Likes" in label_h:
                                summary['total_likes'] = self._parse_int(value_str)
                                logger.debug(f"Found X Total Likes: {summary['total_likes']}")
                            elif "Total Posts" in label_h:
                                summary['total_posts'] = self._parse_int(value_str)
                                logger.debug(f"Found X Total Posts: {summary['total_posts']}")

                if len(row) > 7 and row[7] and row[7].strip().isdigit():
                    if i == 1:
                        potential_total = self._parse_int(row[7])
                        if potential_total > 0:
                            summary['total_impressions'] = potential_total
                            logger.debug(f"Found X Total Impressions in data row: {summary['total_impressions']}")

            logger.info(f"X summary parsed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error parsing X summary: {str(e)}", exc_info=True)
            return summary

    def parse_summary_reddit(self, rows: List[List[str]]) -> Dict[str, int]:
        logger.info("Parsing Reddit summary statistics")

        summary = {
            'total_views': 0,
            'total_upvotes': 0,
            'total_posts': 0
        }

        try:
            for i, row in enumerate(rows):
                if i == 0:
                    continue

                if len(row) > 15:
                    label_p = row[15].strip() if row[15] else ""

                    if "Total Impressions" in label_p or "Total Views" in label_p or "Total Upvotes" in label_p or "Total Posts" in label_p:
                        if i + 1 < len(rows) and len(rows[i + 1]) > 15:
                            value_str = rows[i + 1][15].strip() if rows[i + 1][15] else "0"

                            if "Total Impressions" in label_p or "Total Views" in label_p:
                                summary['total_views'] = self._parse_int(value_str)
                                logger.debug(f"Found Reddit Total Views: {summary['total_views']}")
                            elif "Total Upvotes" in label_p:
                                summary['total_upvotes'] = self._parse_int(value_str)
                                logger.debug(f"Found Reddit Total Upvotes: {summary['total_upvotes']}")
                            elif "Total Posts" in label_p:
                                summary['total_posts'] = self._parse_int(value_str)
                                logger.debug(f"Found Reddit Total Posts: {summary['total_posts']}")

                if len(row) > 15 and row[15] and row[15].strip().isdigit():
                    if i == 1:
                        potential_total = self._parse_int(row[15])
                        if potential_total >= 0:
                            summary['total_views'] = potential_total
                            logger.debug(f"Found Reddit Total Views in data row: {summary['total_views']}")

            logger.info(f"Reddit summary parsed: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error parsing Reddit summary: {str(e)}", exc_info=True)
            return summary

    def parse_individual_posts(self, rows: List[List[str]], year_month: str) -> List[Dict]:
        logger.info(f"Parsing individual posts for {year_month}")

        posts = []

        try:
            for i, row in enumerate(rows):
                row_num = i + 1

                if i < 1:
                    continue

                if i >= self.summary_start_row - 1:
                    break

                if self._has_x_post(row):
                    post = self._parse_x_post(row, year_month, row_num)
                    if post:
                        posts.append(post)
                        logger.debug(f"Row {row_num}: Parsed X post from {post['author']}")

                if self._has_reddit_post(row):
                    post = self._parse_reddit_post(row, year_month, row_num)
                    if post:
                        posts.append(post)
                        logger.debug(f"Row {row_num}: Parsed Reddit post from {post['author']}")

            logger.info(f"Parsed {len(posts)} total posts")
            return posts

        except Exception as e:
            logger.error(f"Error parsing individual posts: {str(e)}", exc_info=True)
            return posts

    def _has_x_post(self, row: List[str]) -> bool:
        return len(row) > 2 and bool(row[2].strip() if row[2] else False)

    def _has_reddit_post(self, row: List[str]) -> bool:
        return len(row) > 10 and bool(row[10].strip() if row[10] else False)

    def _parse_x_post(self, row: List[str], year_month: str, row_num: int) -> Optional[Dict]:
        try:
            date_str = row[0].strip() if len(row) > 0 and row[0] else ""
            author = row[1].strip() if len(row) > 1 and row[1] else "Unknown"
            raw_url = row[2].strip() if len(row) > 2 and row[2] else ""
            url = self._normalize_x_url(raw_url)
            if not url:
                logger.warning(f"Row {row_num}: X URL missing status ID; skipping.")
                return None
            impressions = self._parse_int(row[3] if len(row) > 3 else "0")
            likes = self._parse_int(row[4] if len(row) > 4 else "0")
            comments = self._parse_int(row[5] if len(row) > 5 else "0")
            notes = row[6].strip() if len(row) > 6 and row[6] else ""

            date = self._parse_date(date_str, year_month)

            return {
                'year_month': year_month,
                'date': date,
                'platform': 'x',
                'author': author,
                'url': url,
                'impressions_or_views': impressions,
                'likes': likes,
                'comments': comments,
                'notes': notes,
                'row_num': row_num
            }

        except Exception as e:
            logger.warning(f"Failed to parse X post at row {row_num}: {str(e)}")
            return None

    def _parse_reddit_post(self, row: List[str], year_month: str, row_num: int) -> Optional[Dict]:
        try:
            date_str = row[8].strip() if len(row) > 8 and row[8] else ""
            author = row[9].strip() if len(row) > 9 and row[9] else "Unknown"
            url = row[10].strip() if len(row) > 10 and row[10] else ""
            views = self._parse_int(row[11] if len(row) > 11 else "0")
            upvotes = self._parse_int(row[12] if len(row) > 12 else "0")
            comments = self._parse_int(row[13] if len(row) > 13 else "0")
            notes = row[14].strip() if len(row) > 14 and row[14] else ""

            date = self._parse_date(date_str, year_month)

            return {
                'year_month': year_month,
                'date': date,
                'platform': 'reddit',
                'author': author,
                'url': url,
                'impressions_or_views': views,
                'upvotes': upvotes,
                'comments': comments,
                'notes': notes,
                'row_num': row_num
            }

        except Exception as e:
            logger.warning(f"Failed to parse Reddit post at row {row_num}: {str(e)}")
            return None

    def _parse_int(self, value: str) -> int:
        try:
            clean = re.sub(r'[^\d-]', '', str(value))
            return int(clean) if clean and clean != '-' else 0
        except (ValueError, TypeError):
            return 0

    def _parse_date(self, date_str: str, year_month: str) -> str:
        try:
            if not date_str:
                return f"{year_month}-01"

            parts = date_str.split('/')
            if len(parts) == 3:
                day, month, year = parts
                if len(year) == 2:
                    year = f"20{year}"
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            return f"{year_month}-01"

        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {str(e)}")
            return f"{year_month}-01"

    def _normalize_x_url(self, url: str) -> Optional[str]:
        if not url:
            return None
        if url.isdigit():
            return f"https://x.com/i/status/{url}"
        match = re.search(r"/status(?:es)?/(\d+)", url)
        if match:
            return f"https://x.com/i/status/{match.group(1)}"
        return None
