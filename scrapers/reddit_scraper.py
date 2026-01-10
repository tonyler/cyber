import time
from datetime import datetime
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

    def scrape_reddit_comments(self, post_url: str) -> List[Dict]:
        logger.info(f"Scraping comments from: {post_url}")

        comments = []

        try:
            if 'old.reddit.com' not in post_url:
                post_url = post_url.replace('reddit.com', 'old.reddit.com')

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
            comments = self.scrape_reddit_comments(url)
            matched_comments = self.match_comments_to_members(comments)

            if matched_comments:
                self.write_comments_to_sheet(matched_comments, url)

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
