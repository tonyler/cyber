import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build

from base_scraper import BaseScraper, logger
from sheet_stats_updater import SheetStatsUpdater

class RedditScraper(BaseScraper):
    def __init__(self, members_db_path: str, links_db_path: str, activity_sheet_id: str,
                 credentials_file: str, headless: bool = True,
                 stats_sheet_id: str = None, sheet_config: Dict = None,
                 verbose_metrics: bool = False):
        super().__init__(members_db_path, links_db_path, headless)
        self.activity_sheet_id = activity_sheet_id
        self.credentials_file = credentials_file
        self.stats_sheet_id = stats_sheet_id
        self.sheet_config = sheet_config or {}
        self.stats_updater = None
        self.verbose_metrics = verbose_metrics
        self._init_sheets_service()
        if self.stats_sheet_id and self.sheet_config:
            self.stats_updater = SheetStatsUpdater(
                credentials_file=self.credentials_file,
                spreadsheet_id=self.stats_sheet_id,
                config=self.sheet_config
            )

    def _init_sheets_service(self):
        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_file,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.sheets_service = build('sheets', 'v4', credentials=credentials)

    def get_reddit_links_to_scrape(self, year_month: str = None) -> List[Dict]:
        if not year_month:
            year_month = datetime.now().strftime("%Y-%m")

        logger.info(f"Fetching Reddit links for {year_month}...")
        try:
            links = self.links_db.get_links_for_month_and_platform(year_month, 'reddit')
            logger.info(f"Found {len(links)} Reddit links to scrape")
            return links
        except Exception as e:
            logger.error(f"Error fetching Reddit links: {str(e)}", exc_info=True)
            return []

    def _to_old_reddit(self, url: str) -> str:
        """Convert any Reddit URL to old.reddit.com format"""
        if 'old.reddit.com' in url:
            return url
        url = url.replace('www.reddit.com', 'old.reddit.com')
        url = url.replace('://reddit.com', '://old.reddit.com')
        return url

    def scrape_post_metrics(self, post_url: str) -> Dict[str, int]:
        """Scrape upvotes and comment count from Reddit post (old.reddit.com)"""
        metrics = {'upvotes': 0, 'comments': 0}

        try:
            # Convert to old.reddit.com if needed
            post_url = self._to_old_reddit(post_url)

            # Handle share URLs (reddit.com/r/sub/s/xxx)
            if '/s/' in post_url:
                self._safe_get(post_url)
                time.sleep(2)
                post_url = self._to_old_reddit(self.page.url)
                self._safe_get(post_url)
                time.sleep(2)

            # Extract upvotes - try multiple selectors for old.reddit.com
            score_selectors = [
                '.thing.link .score.unvoted',
                '.thing.link .score.likes',
                '.thing.link .score.dislikes',
                '.sitetable .score.unvoted',
                '.sitetable .score',
                '.linkinfo .score .number',
            ]
            for selector in score_selectors:
                try:
                    score_el = self.page.locator(selector).first
                    if score_el.count() > 0:
                        score_text = score_el.text_content() or '0'
                        # Parse "123 points", "123", or just a number
                        clean_text = score_text.replace(',', '').strip()
                        match = re.search(r'(\d+)', clean_text)
                        if match:
                            metrics['upvotes'] = int(match.group(1))
                            break
                except Exception:
                    continue

            # Extract comment count - try multiple selectors
            comment_selectors = [
                '.thing.link a.comments',
                '.sitetable a.comments',
                '.linkinfo .comments .number',
            ]
            for selector in comment_selectors:
                try:
                    comments_el = self.page.locator(selector).first
                    if comments_el.count() > 0:
                        comments_text = comments_el.text_content() or '0'
                        # Parse "42 comments" or "comment"
                        match = re.search(r'(\d+)', comments_text)
                        if match:
                            metrics['comments'] = int(match.group(1))
                            break
                except Exception:
                    continue

            if self.verbose_metrics:
                logger.info(f"Reddit metrics for {post_url}: upvotes={metrics['upvotes']}, comments={metrics['comments']}")

        except Exception as e:
            logger.warning(f"Error scraping Reddit metrics: {e}")

        return metrics

    def scrape_reddit_comments(self, post_url: str) -> List[Dict]:
        logger.info(f"Scraping comments from: {post_url}")

        comments = []

        try:
            post_url = self._to_old_reddit(post_url)
            self._safe_get(post_url)
            time.sleep(3)

            comment_elements = self.page.locator('.comment').all()
            logger.info(f"Found {len(comment_elements)} comment elements")
            if not comment_elements:
                logger.warning(f"No Reddit comment elements found on {post_url}; skipping.")
                return comments

            for element in comment_elements:
                try:
                    comment_data = self._extract_comment_data(element, post_url)
                    if comment_data:
                        comments.append(comment_data)
                except Exception as e:
                    logger.debug(f"Error extracting comment data: {str(e)}")

            logger.info(f"Extracted {len(comments)} comments")

        except Exception as e:
            logger.error(f"Error scraping Reddit comments: {str(e)}", exc_info=True)

        return comments

    def _extract_comment_data(self, element, post_url: str) -> Dict:
        try:
            # Extract username
            author_element = element.locator('.author').first
            username = author_element.text_content() if author_element.count() > 0 else None

            # Extract text
            text_element = element.locator('.usertext-body').first
            text = text_element.text_content() if text_element.count() > 0 else ''

            # Extract score
            score_element = element.locator('.score').first
            score_text = score_element.text_content() if score_element.count() > 0 else '0'

            score = 0
            try:
                if score_text and score_text != '[score hidden]':
                    score = int(score_text.split()[0])
            except Exception:
                score = 0

            # Extract comment URL
            permalink_element = element.locator('a.bylink').first
            comment_url = None
            if permalink_element.count() > 0:
                href = permalink_element.get_attribute('href')
                if href:
                    comment_url = f"https://old.reddit.com{href}" if href.startswith('/') else href

            if not username or username == '[deleted]':
                return None

            return {
                'username': username,
                'text': text[:200],
                'url': comment_url,
                'score': score,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.debug(f"Error extracting comment data: {str(e)}")
            return None

    def match_comments_to_members(self, comments: List[Dict]) -> List[Dict]:
        """Match Reddit comments to registered members"""
        matched = []

        for comment in comments:
            username = comment.get('username')
            if not username:
                continue

            member = self.find_member_by_reddit_username(username)

            if member:
                logger.info(f"Matched comment from {username} to member {member['discord_user']}")
                matched.append({
                    'discord_user': member['discord_user'],
                    'reddit_username': member['reddit_username'],
                    'comment': comment
                })

        logger.info(f"Matched {len(matched)}/{len(comments)} comments to registered members")
        return matched

    def _get_existing_csv_activity_urls(self, csv_path: Path) -> set:
        """Get set of activity URLs already in CSV to prevent duplicates"""
        if not csv_path.exists():
            return set()

        existing_urls = set()
        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get('activity_url', '').strip()
                    if url:
                        existing_urls.add(url)
        except Exception as e:
            logger.warning(f"Could not read existing CSV data: {e}")
            return set()

        return existing_urls

    def write_activities_to_csv(self, activities: List[Dict], target_url: str):
        """Write activities to reddit_activity_log.csv (append-only)"""
        if not activities:
            logger.info("No activities to write to CSV")
            return

        csv_path = Path(__file__).parent.parent / "database" / "reddit_activity_log.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        headers = [
            'date', 'time', 'discord_user', 'reddit_username', 'activity_type',
            'activity_url', 'target_url', 'task_id', 'notes'
        ]

        file_exists = csv_path.exists()
        existing_urls = self._get_existing_csv_activity_urls(csv_path)

        try:
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                if not file_exists:
                    writer.writerow(headers)
                    logger.info(f"Created new CSV file: {csv_path}")

                new_count = 0
                skipped_count = 0

                for item in activities:
                    comment = item['comment']
                    activity_url = comment.get('url', '')

                    if activity_url in existing_urls:
                        skipped_count += 1
                        continue

                    row = [
                        datetime.now().strftime('%Y-%m-%d'),
                        datetime.now().strftime('%H:%M:%S'),
                        item['discord_user'],
                        item['reddit_username'],
                        'comment',
                        activity_url,
                        target_url,
                        '',
                        comment.get('text', '')[:500]
                    ]
                    writer.writerow(row)
                    existing_urls.add(activity_url)
                    new_count += 1

                if new_count > 0:
                    logger.info(f"✅ Wrote {new_count} new activities to CSV: {csv_path}")
                if skipped_count > 0:
                    logger.info(f"⏭️  Skipped {skipped_count} duplicate activities already in CSV")

        except Exception as e:
            logger.error(f"Failed to write activities to CSV: {e}", exc_info=True)

    def _update_metrics_csv(self, target_url: str, metrics: Dict[str, int]):
        """Update metrics (upvotes, comments) in links.csv"""
        csv_path = Path(__file__).parent.parent / "database" / "links.csv"
        if not csv_path.exists():
            logger.warning("links.csv not found")
            return

        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
        except Exception as e:
            logger.warning(f"Failed to read links.csv: {e}")
            return

        if not fieldnames:
            return

        updated = False
        for row in rows:
            row_url = row.get('url', '').strip()
            # Normalize URLs for comparison
            if self._urls_match(row_url, target_url):
                row['likes'] = str(metrics.get('upvotes', 0))
                row['comments'] = str(metrics.get('comments', 0))
                updated = True
                break

        if not updated:
            logger.debug(f"URL not found in links.csv: {target_url}")
            return

        tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
        try:
            with tmp_path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            tmp_path.replace(csv_path)
            logger.info(f"✅ Updated metrics in CSV for {target_url}")
        except Exception as e:
            logger.warning(f"Failed to write links.csv: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _urls_match(self, url1: str, url2: str) -> bool:
        """Check if two Reddit URLs refer to the same post"""
        def normalize(url: str) -> str:
            url = url.lower().strip().rstrip('/')
            url = url.replace('www.reddit.com', 'reddit.com')
            url = url.replace('old.reddit.com', 'reddit.com')
            # Extract post ID if present
            match = re.search(r'/comments/([a-z0-9]+)', url)
            if match:
                return match.group(1)
            return url
        return normalize(url1) == normalize(url2)

    def _update_stats_sheet(self, link: Dict, metrics: Dict[str, int]):
        """Update stats in Google Sheets"""
        if not self.stats_updater:
            return

        url = link.get('url', '')
        year_month = link.get('year_month') or datetime.now().strftime("%Y-%m")
        sheet_name = self.stats_updater.format_sheet_name(year_month)
        columns = self.sheet_config.get('sheet_template', {}).get('reddit_columns', {})

        url_col = columns.get('url', 'C')
        upvotes_col = columns.get('upvotes', 'E')
        comments_col = columns.get('comments', 'F')

        row_num = self.stats_updater.find_row_by_url(sheet_name, url_col, url)
        if not row_num:
            logger.debug(f"Reddit URL not found in sheet {sheet_name}: {url}")
            return

        values = [metrics.get('upvotes', 0), metrics.get('comments', 0)]
        success = self.stats_updater.update_row_range(
            sheet_name, upvotes_col, comments_col, row_num, values
        )

        if success:
            logger.info(f"✅ Updated Reddit stats for row {row_num}")

    def _sync_impressions_from_sheet(self, link: Dict):
        """Sync impressions (views) from Google Sheet back to CSV (for manually added data)"""
        if not self.stats_updater:
            return

        url = link.get('url', '')
        year_month = link.get('year_month') or datetime.now().strftime("%Y-%m")
        sheet_name = self.stats_updater.format_sheet_name(year_month)
        columns = self.sheet_config.get('sheet_template', {}).get('reddit_columns', {})

        url_col = columns.get('url', 'C')
        views_col = columns.get('views', 'D')

        row_num = self.stats_updater.find_row_by_url(sheet_name, url_col, url)
        if not row_num:
            return

        # Read impressions value from sheet
        try:
            range_name = f"'{sheet_name}'!{views_col}{row_num}"
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.stats_sheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [[]])
            impressions_str = values[0][0] if values and values[0] else ''
        except Exception as e:
            logger.debug(f"Could not read impressions from sheet: {e}")
            return

        if not impressions_str:
            return

        # Parse impressions value
        try:
            impressions = int(str(impressions_str).replace(',', '').strip())
        except (ValueError, TypeError):
            return

        # Update links.csv with impressions
        csv_path = Path(__file__).parent.parent / "database" / "links.csv"
        if not csv_path.exists():
            return

        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
        except Exception:
            return

        if not fieldnames:
            return

        updated = False
        for row in rows:
            if self._urls_match(row.get('url', ''), url):
                current_impressions = row.get('impressions', '')
                if str(impressions) != str(current_impressions):
                    row['impressions'] = str(impressions)
                    updated = True
                    logger.info(f"📥 Synced impressions from sheet: {impressions} for {url}")
                break

        if updated:
            tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
            try:
                with tmp_path.open('w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                tmp_path.replace(csv_path)
            except Exception as e:
                logger.warning(f"Failed to sync impressions to CSV: {e}")
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

    def _get_current_month_tab(self) -> str:
        """Get current month tab name based on config format (e.g., '01/26')"""
        now = datetime.now()
        month_tab_format = self.sheet_config.get('sync', {}).get('month_tab_format', 'MM/YY')

        if month_tab_format == 'MM/YYYY':
            return now.strftime('%m/%Y')
        else:  # Default to MM/YY
            return now.strftime('%m/%y')

    def write_comments_to_sheet(self, matched_comments: List[Dict], target_url: str):
        """Write matched comments to Google Sheets monthly tab"""
        if not matched_comments:
            logger.info("No comments to write")
            return

        # Get current month tab name (e.g., "01/26")
        month_tab = self._get_current_month_tab()
        logger.info(f"Writing {len(matched_comments)} comments to {month_tab} tab...")

        try:
            rows = []

            for item in matched_comments:
                comment = item['comment']
                date = datetime.now().strftime('%Y-%m-%d')
                time_str = datetime.now().strftime('%H:%M:%S')

                # Column structure: date, time, discord_user, reddit_username, activity_type,
                # activity_url, target_url, task_id, score, engagement, notes
                row = [
                    date,                               # M: date
                    time_str,                           # N: time
                    item['discord_user'],               # O: discord_user
                    item['reddit_username'],            # P: reddit_username
                    'comment',                          # Q: activity_type
                    comment.get('url', ''),             # R: activity_url
                    target_url,                         # S: target_url
                    '',                                 # T: task_id (empty for now)
                    comment.get('score', 0),            # U: score (Reddit uses score instead of impressions)
                    0,                                  # V: engagement (0 for now)
                    comment.get('text', '')[:500]       # W: notes (comment text, limited to 500 chars)
                ]
                rows.append(row)

            # Reddit activities go to columns M-W in monthly tab
            range_name = f"'{month_tab}'!M:W"

            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.activity_sheet_id,
                range=range_name
            ).execute()

            existing_rows = result.get('values', [])
            next_row = len(existing_rows) + 1

            body = {'values': rows}

            result = self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.activity_sheet_id,
                range=f"'{month_tab}'!M{next_row}",
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(f"✅ Wrote {result.get('updates', {}).get('updatedRows', 0)} rows to {month_tab} tab")

        except Exception as e:
            logger.error(f"❌ Error writing to sheet: {str(e)}", exc_info=True)

    def scrape_link(self, link: Dict) -> int:
        """Scrape a single Reddit link"""
        url = link['url']
        logger.info("=" * 80)
        logger.info(f"Scraping Reddit link: {url}")
        logger.info("=" * 80)

        try:
            # First, sync impressions from sheet (reverse sync for manually added data)
            self._sync_impressions_from_sheet(link)

            # Scrape comments (this navigates to the page)
            comments = self.scrape_reddit_comments(url)

            # Scrape post metrics (upvotes, comment count) - page already loaded
            metrics = self.scrape_post_metrics(url)
            logger.info(f"Reddit metrics: upvotes={metrics['upvotes']}, comments={metrics['comments']}")

            # Match comments to members
            matched_comments = self.match_comments_to_members(comments)

            # Write activities to sheet and CSV
            if matched_comments:
                self.write_comments_to_sheet(matched_comments, url)
                self.write_activities_to_csv(matched_comments, url)

            # Update stats in CSV and Google Sheet
            self._update_metrics_csv(url, metrics)
            self._update_stats_sheet(link, metrics)

            return len(matched_comments)

        except Exception as e:
            logger.error(f"Error scraping link {url}: {str(e)}", exc_info=True)
            return 0

    def run(self, year_month: str = None, limit: int = None):
        """Run the Reddit scraper"""
        logger.info("=" * 80)
        logger.info("REDDIT SCRAPER STARTED")
        logger.info("=" * 80)

        links = self.get_reddit_links_to_scrape(year_month)

        if limit:
            links = links[:limit]
            logger.info(f"Limited to {limit} links")

        if not links:
            logger.info("No Reddit links to scrape")
            return

        self._init_browser()

        total_matched = 0

        for i, link in enumerate(links, 1):
            logger.info(f"Processing link {i}/{len(links)}")
            matched_count = self.scrape_link(link)
            total_matched += matched_count
            time.sleep(2)

        logger.info("=" * 80)
        logger.info("REDDIT SCRAPER COMPLETED")
        logger.info(f"Total links scraped: {len(links)}")
        logger.info(f"Total member comments found: {total_matched}")
        logger.info("=" * 80)
