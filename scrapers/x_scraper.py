import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
from google.oauth2 import service_account
from googleapiclient.discovery import build

from base_scraper import BaseScraper, logger
from sheet_stats_updater import SheetStatsUpdater

class XScraper(BaseScraper):
    def __init__(self, members_db_path: str, links_db_path: str, activity_sheet_id: str,
                 credentials_file: str, headless: bool = True, session_file: str = None,
                 stats_sheet_id: str = None, sheet_config: Dict = None,
                 verbose_metrics: bool = False):
        super().__init__(members_db_path, links_db_path, headless)
        self.activity_sheet_id = activity_sheet_id
        self.credentials_file = credentials_file
        self.stats_sheet_id = stats_sheet_id
        self.sheet_config = sheet_config or {}
        self.stats_updater = None
        self.verbose_metrics = verbose_metrics
        if session_file:
            self.session_file = session_file
        else:
            self.session_file = str(Path(__file__).parent.parent / "shared" / "x_session.json")
        self._init_sheets_service()
        if self.stats_sheet_id and self.sheet_config:
            self.stats_updater = SheetStatsUpdater(
                credentials_file=self.credentials_file,
                spreadsheet_id=self.stats_sheet_id,
                config=self.sheet_config
            )

    def _init_browser(self):
        """Override to apply X session cookies after browser init"""
        super()._init_browser()
        self._apply_x_session()

    def _apply_x_session(self):
        """Load and apply X session cookies"""
        session_path = Path(self.session_file)
        if not session_path.exists():
            logger.warning(f"X session file not found: {session_path}")
            return

        try:
            with session_path.open('r') as f:
                session_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read X session file: {e}", exc_info=True)
            return

        cookies = session_data.get('cookies', [])
        if not isinstance(cookies, list) or not cookies:
            logger.warning("X session file has no cookies to load")
            return

        # Group cookies by domain
        cookies_by_domain = {}
        for cookie in cookies:
            domain = cookie.get('domain', 'x.com').lstrip('.')
            cookies_by_domain.setdefault(domain, []).append(cookie)

        # Apply cookies for each domain
        for domain, domain_cookies in cookies_by_domain.items():
            try:
                self.page.goto(f"https://{domain}/")
                time.sleep(1)

                for cookie in domain_cookies:
                    playwright_cookie = self._normalize_cookie(cookie, domain)
                    if playwright_cookie:
                        try:
                            self.context.add_cookies([playwright_cookie])
                        except Exception as e:
                            logger.debug(f"Failed to add cookie {cookie.get('name')}: {e}")
            except Exception as e:
                logger.warning(f"Failed to apply cookies for {domain}: {e}")

        logger.info(
            f"Applied X session cookies for {len(cookies_by_domain)} domain(s) "
            f"({sum(len(v) for v in cookies_by_domain.values())} cookies)"
        )

        self._verify_logged_in()

    def _verify_logged_in(self):
        """Verify X session is logged in"""
        try:
            self.page.goto("https://x.com/home")
            time.sleep(2)

            # Check for auth cookie in context
            cookies = self.context.cookies()
            auth_cookie = next((c for c in cookies if c['name'] == 'auth_token'), None)

            if auth_cookie and auth_cookie.get('value'):
                logger.info("X session appears logged in (auth_token present)")
            else:
                logger.warning("X session auth_token missing; login may be required")
        except Exception as e:
            logger.debug(f"Failed to verify X login: {e}")

    def _normalize_cookie(self, cookie: Dict, domain: str) -> Dict:
        """Convert cookie to Playwright format"""
        name = cookie.get('name')
        value = cookie.get('value')
        if not name or value is None:
            return None

        normalized = {
            'name': name,
            'value': value,
            'domain': domain,
            'path': cookie.get('path', '/'),
        }

        if 'secure' in cookie:
            normalized['secure'] = cookie['secure']
        if 'httpOnly' in cookie:
            normalized['httpOnly'] = cookie['httpOnly']

        expires = cookie.get('expires')
        if isinstance(expires, (int, float)) and expires > 0:
            normalized['expires'] = int(expires)

        return normalized

    def _init_sheets_service(self):
        """Initialize Google Sheets service"""
        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_file,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.sheets_service = build('sheets', 'v4', credentials=credentials)

    def get_x_links_to_scrape(self, year_month: str = None) -> List[Dict]:
        """Get X links to scrape from database"""
        if not year_month:
            year_month = datetime.now().strftime("%Y-%m")

        logger.info(f"Fetching X links for {year_month}...")
        try:
            links = self.links_db.get_links_for_month_and_platform(year_month, 'x')
            logger.info(f"Found {len(links)} X links to scrape")
            return links
        except Exception as e:
            logger.error(f"Error fetching X links: {str(e)}", exc_info=True)
            return []

    def _normalize_x_url(self, url: str) -> str:
        """Ensure URL has proper protocol"""
        if not url:
            return url
        match = re.search(r"/status(?:es)?/(\d+)", url)
        if match:
            return f"https://x.com/i/status/{match.group(1)}"
        if url.isdigit():
            return f"https://x.com/i/status/{url}"
        if url.startswith('http://') or url.startswith('https://'):
            return url
        return f"https://{url.lstrip('/')}"

    def _build_activity_url(self, tweet_url: str, suffix: str) -> str:
        """Build activity URL (quotes, retweets, etc.)"""
        base_url = tweet_url.split('?', 1)[0].rstrip('/')
        return f"{base_url}/{suffix}"

    def _parse_activity_timestamp(self, timestamp: str) -> Tuple[str, str]:
        """Parse timestamp into date and time strings"""
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
            except Exception:
                pass
        now = datetime.now()
        return now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S')

    def _get_current_month_tab(self) -> str:
        """Get current month tab name based on config format (e.g., '01/26')"""
        now = datetime.now()
        month_tab_format = self.sheet_config.get('sync', {}).get('month_tab_format', 'MM/YY')

        if month_tab_format == 'MM/YYYY':
            return now.strftime('%m/%Y')
        else:  # Default to MM/YY
            return now.strftime('%m/%y')

    def _scroll_page(self, scrolls: int = 3):
        """Scroll page to load dynamic content"""
        for _ in range(scrolls):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

<<<<<<< HEAD
    def _scroll_to_end(self, max_scrolls: int = 50, wait_time: float = 2.0):
        """Scroll until no new content loads or max scrolls reached (mobile-optimized)"""
        logger.info("Scrolling to load all content (mobile mode)...")
=======
    def _scroll_to_end(self, max_scrolls: int = 50, wait_time: float = 3.0):
        """Scroll until no new content loads or max scrolls reached"""
        logger.info("Scrolling to load all content...")
>>>>>>> origin/main
        previous_height = 0
        scrolls_without_change = 0
        total_scrolls = 0

        while total_scrolls < max_scrolls:
            # Get current scroll height
            current_height = self.page.evaluate("document.body.scrollHeight")

            # If height hasn't changed for 3 consecutive scrolls, we're at the end
            if current_height == previous_height:
                scrolls_without_change += 1
                if scrolls_without_change >= 3:
                    logger.info(f"Reached end of content after {total_scrolls} scrolls")
                    break
            else:
                scrolls_without_change = 0

            # Scroll down
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(wait_time)

            previous_height = current_height
            total_scrolls += 1

        if total_scrolls >= max_scrolls:
            logger.warning(f"Stopped scrolling after reaching max_scrolls ({max_scrolls})")

        return total_scrolls

    def _extract_tweet_data(self, element) -> Dict:
        """Extract data from a tweet element"""
        try:
            # Extract username - try multiple selectors for robustness
            username = None

            # Try data-testid="User-Name" first (most reliable)
            user_name_element = element.locator('[data-testid="User-Name"]').first
            if user_name_element.count() > 0:
                # Get the link within User-Name
                username_link = user_name_element.locator('a[href^="/"]:not([href*="/status"])').first
                if username_link.count() > 0:
                    href = username_link.get_attribute('href')
                    if href and href.startswith('/'):
                        # Extract username from href (format: /@username or /username)
                        username = href.lstrip('/').split('/')[0].lstrip('@')
<<<<<<< HEAD
                        logger.debug(f"Username extracted via User-Name testid: {username}")
=======
>>>>>>> origin/main

            # Fallback: try to find username from tweet link
            if not username:
                time_element = element.locator('time').first
                if time_element.count() > 0:
                    parent_link = time_element.locator('xpath=..').first
                    if parent_link.count() > 0:
                        tweet_href = parent_link.get_attribute('href')
                        if tweet_href:
                            # Extract username from tweet URL (format: /username/status/ID)
                            parts = tweet_href.lstrip('/').split('/')
                            if len(parts) >= 1:
                                username = parts[0].lstrip('@')
<<<<<<< HEAD
                                logger.debug(f"Username extracted via time element fallback: {username}")

            # Extract text
            text = ''
            text_element = element.locator('[data-testid="tweetText"]').first
            if text_element.count() > 0:
                text = text_element.text_content()
                logger.debug("Tweet text extracted via tweetText testid")
            else:
                # Mobile fallback: try div with lang attribute
                text_element = element.locator('div[lang]').first
                if text_element.count() > 0:
                    text = text_element.text_content()
                    logger.debug("Tweet text extracted via lang attribute fallback (mobile)")
=======

            # Extract text
            text_element = element.locator('[data-testid="tweetText"]').first
            text = text_element.text_content() if text_element.count() > 0 else ''
>>>>>>> origin/main

            # Extract timestamp and URL
            time_element = element.locator('time').first
            tweet_url = None
            timestamp = None
            if time_element.count() > 0:
                timestamp = time_element.get_attribute('datetime')
                parent_link = time_element.locator('xpath=..').first
                if parent_link.count() > 0:
                    href = parent_link.get_attribute('href')
                    if href:
                        # Construct full URL
                        if href.startswith('http'):
                            tweet_url = href
                        else:
                            tweet_url = f"https://x.com{href}" if href.startswith('/') else href

            if not username:
                logger.debug("Could not extract username from tweet element")
                return None

            return {
                'username': username,
                'text': text,
                'url': tweet_url,
                'timestamp': timestamp
            }

        except Exception as e:
            logger.debug(f"Error extracting tweet data: {str(e)}")
            return None

    def scrape_tweet_replies(self, tweet_url: str) -> List[Dict]:
        """Scrape replies to a tweet"""
        tweet_url = self._normalize_x_url(tweet_url)
        logger.info(f"Scraping replies from: {tweet_url}")
        replies = []

        try:
            self._safe_get(tweet_url)
            time.sleep(3)

<<<<<<< HEAD
            # Scroll to load ALL replies - use more aggressive scrolling (mobile-optimized)
            scroll_count = self._scroll_to_end(max_scrolls=100, wait_time=2.0)
=======
            # Scroll to load ALL replies - use more aggressive scrolling
            scroll_count = self._scroll_to_end(max_scrolls=100, wait_time=3.0)
>>>>>>> origin/main
            logger.info(f"Scrolled {scroll_count} times to load all replies")

            tweet_elements = self.page.locator('article').all()
            logger.info(f"Found {len(tweet_elements)} tweet elements")
            if not tweet_elements:
                logger.warning(f"No tweet elements found on {tweet_url}; skipping replies.")
                return replies

            # Extract tweet ID from URL to identify original tweet
            original_tweet_id = None
            match = re.search(r'/status/(\d+)', tweet_url)
            if match:
                original_tweet_id = match.group(1)

            # Process all tweet elements, filtering out the original tweet
            for element in tweet_elements:
                try:
                    reply_data = self._extract_tweet_data(element)
                    if not reply_data:
                        continue

                    # Skip if this is the original tweet (match by tweet ID in URL)
                    reply_url = reply_data.get('url', '')
                    if original_tweet_id and f'/status/{original_tweet_id}' in reply_url:
                        logger.debug(f"Skipping original tweet: {reply_url}")
                        continue

                    reply_data['activity_type'] = 'comment'
                    replies.append(reply_data)
                except Exception as e:
                    logger.debug(f"Error extracting reply data: {str(e)}")

            logger.info(f"Extracted {len(replies)} replies")

        except Exception as e:
            logger.error(f"Error scraping tweet replies: {str(e)}", exc_info=True)

        return replies

    def scrape_tweet_quotes(self, tweet_url: str) -> List[Dict]:
        """Scrape quote tweets"""
        tweet_url = self._normalize_x_url(tweet_url)
        quotes_url = self._build_activity_url(tweet_url, "quotes")
        logger.info(f"Scraping quotes from: {quotes_url}")
        quotes = []

        try:
            self._safe_get(quotes_url)
            time.sleep(3)

<<<<<<< HEAD
            # Scroll to load ALL quote tweets (mobile-optimized)
            scroll_count = self._scroll_to_end(max_scrolls=50, wait_time=1.5)
=======
            # Scroll to load ALL quote tweets
            scroll_count = self._scroll_to_end(max_scrolls=50, wait_time=2.0)
>>>>>>> origin/main
            logger.info(f"Scrolled {scroll_count} times to load all quote tweets")

            tweet_elements = self.page.locator('article').all()
            logger.info(f"Found {len(tweet_elements)} quote tweet elements")
            if not tweet_elements:
                logger.warning(f"No quote tweet elements found on {tweet_url}; skipping quotes.")
                return quotes

            # Extract tweet ID from URL to identify original tweet
            original_tweet_id = None
            match = re.search(r'/status/(\d+)', tweet_url)
            if match:
                original_tweet_id = match.group(1)

            for element in tweet_elements:
                try:
                    quote_data = self._extract_tweet_data(element)
                    if not quote_data:
                        continue

                    # The quote tweet URL is the URL of the person quoting, not the original
                    # So we just collect all quote tweets on this page
                    # The /quotes page should only show quote tweets, not the original
                    quote_data['activity_type'] = 'quote'
                    quotes.append(quote_data)
                except Exception as e:
                    logger.debug(f"Error extracting quote tweet data: {str(e)}")

            logger.info(f"Extracted {len(quotes)} quotes")

        except Exception as e:
            logger.error(f"Error scraping quotes: {str(e)}", exc_info=True)

        return quotes

    def scrape_tweet_reposts(self, tweet_url: str) -> List[Dict]:
        """Scrape retweets/reposts"""
        tweet_url = self._normalize_x_url(tweet_url)
        reposts_url = self._build_activity_url(tweet_url, "retweets")
        logger.info(f"Scraping reposts from: {reposts_url}")
        reposts = []

        try:
            self._safe_get(reposts_url)
            time.sleep(3)

<<<<<<< HEAD
            # Scroll to load ALL reposts (mobile-optimized)
            scroll_count = self._scroll_to_end(max_scrolls=50, wait_time=1.5)
=======
            # Scroll to load ALL reposts
            scroll_count = self._scroll_to_end(max_scrolls=50, wait_time=2.0)
>>>>>>> origin/main
            logger.info(f"Scrolled {scroll_count} times to load all reposts")

            user_cells = self.page.locator('[data-testid="UserCell"]').all()
            logger.info(f"Found {len(user_cells)} repost user cells")
            if not user_cells:
                logger.warning(f"No repost user cells found on {tweet_url}; skipping reposts.")
                return reposts

            for cell in user_cells:
                try:
                    # Get username from the UserCell
                    # Look for the profile link (should be the user's profile, not a status link)
                    link = cell.locator('a[href^="/"]:not([href*="/status"])').first
                    if link.count() == 0:
                        # Fallback to any link
                        link = cell.locator('a[href^="/"]').first
                        if link.count() == 0:
                            continue

                    href = link.get_attribute('href')
                    if not href:
                        continue

                    # Extract username from href (format: /@username or /username)
                    username = href.lstrip('/').split('/')[0].lstrip('@')

                    if not username or username.startswith('i/') or '/status/' in username:
                        continue

                    reposts.append({
                        'username': username,
                        'text': '',
                        'url': f"https://x.com/{username}",
                        'timestamp': None,
                        'activity_type': 'repost'
                    })
                except Exception as e:
                    logger.debug(f"Error extracting repost user: {str(e)}")
                    continue

            logger.info(f"Extracted {len(reposts)} reposts")

        except Exception as e:
            logger.error(f"Error scraping reposts: {str(e)}", exc_info=True)

        return reposts

    def _extract_x_metrics(self, tweet_url: str) -> Dict[str, int]:
        """Extract metrics (views, likes, comments) from tweet"""
        metrics = {
            'impressions': None,
            'likes': None,
            'comments': None,
            'quotes': None,
            'reposts': None,
        }

        try:
            self._safe_get(tweet_url)
            time.sleep(3)

            # Find the main tweet article (should be the first one)
            tweet_article = self.page.locator('article').first
            if tweet_article.count() == 0:
                logger.warning(f"No tweet article found on {tweet_url}")
                return metrics

            # Search for interaction buttons AND view count within the tweet article
            # These elements have aria-label attributes with counts
            elements = tweet_article.locator('[aria-label]').all()

            for element in elements:
                try:
                    label = element.get_attribute('aria-label') or ''
                    if not label:
                        continue

                    # Parse metrics from aria-labels
                    # Format examples: "5 Replies", "10 Reposts", "100 Likes", "1.2K Views"
                    label_lower = label.lower()

                    if 'repl' in label_lower and metrics['comments'] is None:
                        metrics['comments'] = self.parse_count(label)
                    elif 'like' in label_lower and metrics['likes'] is None:
                        metrics['likes'] = self.parse_count(label)
                    elif 'view' in label_lower and metrics['impressions'] is None:
                        metrics['impressions'] = self.parse_count(label)
                    elif 'quote' in label_lower and metrics['quotes'] is None:
                        metrics['quotes'] = self.parse_count(label)
                    elif ('repost' in label_lower or 'retweet' in label_lower) and metrics['reposts'] is None:
                        metrics['reposts'] = self.parse_count(label)

                except Exception as e:
                    logger.debug(f"Error parsing aria-label '{label}': {str(e)}")
                    continue

            # Additional attempt for views - sometimes in span with specific pattern
            if metrics['impressions'] is None:
                try:
                    # Look for analytics link or view count elements
                    view_elements = tweet_article.locator('a[href*="/analytics"], span[data-testid*="views"]').all()
                    for elem in view_elements:
                        text = elem.text_content()
                        if text and ('view' in text.lower() or 'k' in text.lower() or 'm' in text.lower()):
                            count = self.parse_count(text)
                            if count > 0:
                                metrics['impressions'] = count
                                break
                except Exception:
                    pass

            if all(value is None for value in metrics.values()):
                logger.warning(f"No X metrics found on {tweet_url}; selectors may be stale.")
            elif self.verbose_metrics:
                logger.info(
                    "X metrics extracted: impressions=%s likes=%s comments=%s quotes=%s reposts=%s",
                    metrics.get('impressions'),
                    metrics.get('likes'),
                    metrics.get('comments'),
                    metrics.get('quotes'),
                    metrics.get('reposts')
                )

        except Exception as e:
            logger.debug(f"Failed to extract metrics: {e}")

        return metrics

    def _update_stats_sheet(self, link: Dict, metrics: Dict[str, int]):
        """Update stats in Google Sheets"""
        if not self.stats_updater:
            return

        year_month = link.get("year_month") or datetime.now().strftime("%Y-%m")
        sheet_name = self.stats_updater.format_sheet_name(year_month)
        columns = self.sheet_config.get("sheet_template", {}).get("x_columns", {})
        url_col = columns.get("url", "C")
        impressions_col = columns.get("impressions", "D")
        likes_col = columns.get("likes", "E")
        comments_col = columns.get("comments", "F")

        row = self.stats_updater.find_row_by_url(sheet_name, url_col, link.get("url", ""))
        if not row:
            logger.warning(f"X stats row not found for URL: {link.get('url')}")
            return

        success = self.stats_updater.update_row_range(
            sheet_name,
            impressions_col,
            comments_col,
            row,
            [metrics.get('impressions'), metrics.get('likes'), metrics.get('comments')]
        )
        if success:
            logger.info(f"✅ Updated X stats for row {row}")

    def match_activities_to_members(self, activities: List[Dict]) -> List[Dict]:
        """Match activities to registered members"""
        matched = []

        for activity in activities:
            username = activity.get('username')
            if not username:
                continue

            member = self.find_member_by_x_handle(username)

            if member:
                logger.info(
                    f"Matched {activity.get('activity_type', 'activity')} from {username} "
                    f"to member {member['discord_user']}"
                )
                matched.append({
                    'discord_user': member['discord_user'],
                    'x_handle': member['x_handle'],
                    'activity': activity
                })

        logger.info(f"Matched {len(matched)}/{len(activities)} activities to registered members")
        return matched

    def _filter_new_activities(self, activities: List[Dict], target_url: str) -> List[Dict]:
        """Filter out activities that already exist in database"""
        if not activities:
            return []

        existing_urls = self.members_db.get_x_activity_urls_for_target(target_url)
        if not existing_urls:
            return activities

        filtered = []
        for activity in activities:
            activity_url = activity.get('activity', {}).get('url')
            if activity_url and activity_url in existing_urls:
                continue
            filtered.append(activity)

        if self.verbose_metrics:
            logger.info(
                "Filtered %d duplicate X activities for %s",
                len(activities) - len(filtered),
                target_url
            )
        return filtered

    def write_activities_to_sheet(self, activities: List[Dict], target_url: str):
        """Write activities to Google Sheets monthly tab"""
        if not activities:
            logger.info("No activities to write")
            return

        # Get current month tab name (e.g., "01/26")
        month_tab = self._get_current_month_tab()
        logger.info(f"Writing {len(activities)} activities to {month_tab} tab...")

        try:
            rows = []

            for activity in activities:
                activity_data = activity['activity']
                timestamp = activity_data.get('timestamp', '')
                date, time_str = self._parse_activity_timestamp(timestamp)
                activity_type = activity_data.get('activity_type', 'comment')
                activity_url = activity_data.get('url', '')
                if activity_type in ('comment', 'quote'):
                    notes = activity_data.get('text', '')[:500]  # Limit text length
                else:
                    notes = ''

                # Column structure: date, time, discord_user, x_handle, activity_type,
                # activity_url, target_url, task_id, impressions, engagement, notes
                row = [
                    date,                       # A: date
                    time_str,                   # B: time
                    activity['discord_user'],   # C: discord_user
                    activity['x_handle'],       # D: x_handle
                    activity_type,              # E: activity_type
                    activity_url,               # F: activity_url
                    target_url,                 # G: target_url
                    '',                         # H: task_id (empty for now)
                    0,                          # I: impressions (0 for now)
                    0,                          # J: engagement (0 for now)
                    notes                       # K: notes
                ]

                rows.append(row)

            # Write to monthly tab, columns A-K for X activities
            range_name = f"'{month_tab}'!A:K"

            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.activity_sheet_id,
                range=range_name
            ).execute()

            existing_rows = result.get('values', [])
            next_row = len(existing_rows) + 1

            body = {'values': rows}

            result = self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.activity_sheet_id,
                range=f"'{month_tab}'!A{next_row}",
                valueInputOption='RAW',
                body=body
            ).execute()

            logger.info(
                f"✅ Wrote {result.get('updates', {}).get('updatedRows', 0)} rows to {month_tab} tab"
            )

        except Exception as e:
            logger.error(f"❌ Error writing to sheet: {str(e)}", exc_info=True)

    def scrape_link(self, link: Dict) -> int:
        """Scrape a single X link"""
        url = self._normalize_x_url(link['url'])
        logger.info("=" * 80)
        logger.info(f"Scraping X link: {url}")
        logger.info("=" * 80)

        try:
            # Scrape all activity types
            replies = self.scrape_tweet_replies(url)
            quotes = self.scrape_tweet_quotes(url)
            reposts = self.scrape_tweet_reposts(url)

            # Extract metrics
            metrics = self._extract_x_metrics(url)

            # Adjust metrics based on scraped data
            total_reposts = metrics.get('reposts')
            if reposts:
                metrics['reposts'] = len(reposts)
                if total_reposts is not None and total_reposts >= len(reposts):
                    inferred_quotes = total_reposts - len(reposts)
                    if inferred_quotes > 0:
                        metrics['quotes'] = max(metrics.get('quotes') or 0, inferred_quotes)
            if quotes:
                metrics['quotes'] = max(metrics.get('quotes') or 0, len(quotes))

            if self.verbose_metrics:
                logger.info(
                    "X activity counts: replies=%s quotes=%s reposts=%s",
                    len(replies),
                    len(quotes),
                    len(reposts)
                )
                logger.info(
                    "X metrics final: impressions=%s likes=%s comments=%s quotes=%s reposts=%s",
                    metrics.get('impressions'),
                    metrics.get('likes'),
                    metrics.get('comments'),
                    metrics.get('quotes'),
                    metrics.get('reposts')
                )

            # Combine and match activities
            all_activities = replies + quotes + reposts
            matched_activities = self.match_activities_to_members(all_activities)

            # Filter out duplicates
            matched_activities = self._filter_new_activities(matched_activities, url)
            if matched_activities:
                self.write_activities_to_sheet(matched_activities, url)

            # Update stats sheet
            if metrics and any(value is not None for value in metrics.values()):
                self._update_stats_sheet(link, metrics)

            return len(matched_activities)

        except Exception as e:
            logger.error(f"Error scraping link {url}: {str(e)}", exc_info=True)
            return 0

    def run(self, year_month: str = None, limit: int = None):
        """Run the X scraper"""
        logger.info("=" * 80)
        logger.info("X SCRAPER STARTED")
        logger.info("=" * 80)

        links = self.get_x_links_to_scrape(year_month)

        if limit:
            links = links[:limit]
            logger.info(f"Limited to {limit} links")

        if not links:
            logger.info("No X links to scrape")
            return

        self._init_browser()

        total_matched = 0

        for i, link in enumerate(links, 1):
            logger.info(f"Processing link {i}/{len(links)}")
            matched_count = self.scrape_link(link)
            total_matched += matched_count
            time.sleep(2)

        logger.info("=" * 80)
        logger.info("X SCRAPER COMPLETED")
        logger.info(f"Total links scraped: {len(links)}")
        logger.info(f"Total member activities found: {total_matched}")
        logger.info("=" * 80)
