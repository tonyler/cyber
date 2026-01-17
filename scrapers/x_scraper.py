import json
import re
import time
import csv
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

    def _click_show_more_replies(self):
        """Click 'Show' buttons to reveal hidden/spam replies"""
        try:
            # Look for various "Show" button patterns
            show_buttons = self.page.locator('span:has-text("Show")').all()
            clicked = 0
            for button in show_buttons:
                try:
                    if button.is_visible():
                        button.click()
                        clicked += 1
                        time.sleep(0.5)
                except Exception:
                    continue
            if clicked > 0:
                logger.info(f"Clicked {clicked} 'Show' buttons to reveal hidden replies")
                time.sleep(2)  # Wait for content to load
        except Exception as e:
            logger.debug(f"Error clicking show buttons: {e}")

    def _scroll_page(self, scrolls: int = 3):
        """Scroll page to load dynamic content"""
        for _ in range(scrolls):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

    def _scroll_to_end(self, max_scrolls: int = 50, wait_time: float = 2.0):
        """Scroll until no new content loads or max scrolls reached (mobile-optimized)"""
        logger.info("Scrolling to load all content (mobile mode)...")
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
                        logger.debug(f"Username extracted via User-Name testid: {username}")

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

            # Click "Show" buttons for hidden/spam replies
            self._click_show_more_replies()

            # Scroll to load ALL replies - slower for mobile to ensure content loads
            scroll_count = self._scroll_to_end(max_scrolls=100, wait_time=3.5)
            logger.info(f"Scrolled {scroll_count} times to load all replies")

            # Click show buttons again after scrolling in case new ones appeared
            self._click_show_more_replies()

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

            # Scroll to load ALL quote tweets - slower for mobile
            scroll_count = self._scroll_to_end(max_scrolls=50, wait_time=3.0)
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

            # Scroll to load ALL reposts - slower for mobile
            scroll_count = self._scroll_to_end(max_scrolls=50, wait_time=3.0)
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

    def _find_target_article(self, tweet_url: str):
        """Find the article element matching the target tweet URL.

        When viewing a reply/comment, X shows the parent tweet first,
        then the reply. We need to find the article that matches our target URL.
        """
        # Extract tweet ID from URL
        match = re.search(r'/status/(\d+)', tweet_url)
        if not match:
            logger.warning(f"Could not extract tweet ID from URL: {tweet_url}")
            return self.page.locator('article').first

        target_tweet_id = match.group(1)
        logger.debug(f"Looking for article with tweet ID: {target_tweet_id}")

        # Find all articles on the page
        articles = self.page.locator('article').all()
        logger.debug(f"Found {len(articles)} articles on page")

        for article in articles:
            try:
                # Look for a time element with a link to this specific tweet
                time_links = article.locator('time').locator('xpath=..').all()
                for time_link in time_links:
                    href = time_link.get_attribute('href') or ''
                    if f'/status/{target_tweet_id}' in href:
                        logger.debug(f"Found matching article for tweet {target_tweet_id}")
                        return article
            except Exception as e:
                logger.debug(f"Error checking article: {e}")
                continue

        # Fallback: if this is a reply page, the target tweet is the 2nd article
        # (1st is parent, 2nd is the reply we're viewing)
        # Check if first article is a DIFFERENT tweet (meaning we're viewing a reply)
        if len(articles) >= 2:
            first_article = articles[0]
            try:
                first_time_links = first_article.locator('time').locator('xpath=..').all()
                for time_link in first_time_links:
                    href = time_link.get_attribute('href') or ''
                    # If first article has a different tweet ID, this is a reply page
                    if '/status/' in href and f'/status/{target_tweet_id}' not in href:
                        logger.debug(f"First article is parent tweet; using 2nd article for reply {target_tweet_id}")
                        return articles[1]
            except Exception as e:
                logger.debug(f"Error checking first article: {e}")

        # Final fallback: use first article (standalone tweet)
        logger.debug("Using first article as fallback (likely standalone tweet)")
        return self.page.locator('article').first

    def _extract_x_metrics(self, tweet_url: str) -> Dict[str, int]:
        """Extract metrics (views, likes, comments) from tweet"""
        metrics = {
            'impressions': None,
            'likes': None,
            'comments': None,
            'quotes': None,
            'reposts': None,
            'content': None,
        }

        try:
            self._safe_get(tweet_url)
            time.sleep(3)

            # Find the article matching our target tweet (handles replies correctly)
            tweet_article = self._find_target_article(tweet_url)
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

            # Additional attempts for views on mobile
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

            # Mobile-specific: look for view count in text content
            if metrics['impressions'] is None:
                try:
                    # Search all text nodes for view count pattern
                    all_text_elements = tweet_article.locator('*').all()
                    for elem in all_text_elements:
                        try:
                            text = elem.text_content() or ''
                            # Match patterns like "1.2K Views", "Views 1.2K", or just numbers with K/M
                            if 'view' in text.lower():
                                # Extract number before or after "views"
                                match = re.search(r'([\d,.]+[KMB]?)\s*views?|views?\s*([\d,.]+[KMB]?)', text, re.IGNORECASE)
                                if match:
                                    count_str = match.group(1) or match.group(2)
                                    count = self.parse_count(count_str)
                                    if count > 0:
                                        metrics['impressions'] = count
                                        logger.debug(f"Found views in text: {text} -> {count}")
                                        break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"Error searching for mobile view count: {e}")

            metric_values = [
                metrics.get('impressions'),
                metrics.get('likes'),
                metrics.get('comments'),
                metrics.get('quotes'),
                metrics.get('reposts'),
            ]
            if all(value is None for value in metric_values):
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

            # Extract main tweet content for local storage
            # Check for X article first (long-form content)
            try:
                article_view = tweet_article.locator('[data-testid="twitterArticleReadView"]').first

                if article_view.count() > 0:
                    # This is an X article - extract title only
                    article_text = article_view.text_content() or ""
                    # Title is at the start, before metrics numbers (e.g., "15822335110K")
                    title_match = re.match(r'^(.+?)(?:\s*\d+[KMB]?\s*\d+[KMB]?\s*\d+[KMB]?\s*\d+[KMB]?|$)', article_text)
                    if title_match:
                        article_title = title_match.group(1).strip()
                    else:
                        # Fallback: take first 200 chars and cut at sentence end
                        article_title = article_text[:200].rsplit('.', 1)[0] if '.' in article_text[:200] else article_text[:100]
                    if article_title:
                        metrics['content'] = f"[Article] {article_title}"
                        metrics['is_article'] = True
                        logger.info(f"Detected X article: {article_title[:60]}...")
                else:
                    # Regular tweet - extract full text
                    text_element = tweet_article.locator('[data-testid="tweetText"]').first
                    if text_element.count() > 0:
                        text = text_element.text_content()
                        if text:
                            metrics['content'] = text.strip()
            except Exception as e:
                logger.debug(f"Failed to extract tweet content: {e}")

        except Exception as e:
            logger.debug(f"Failed to extract metrics: {e}")

        return metrics

    def _update_task_content_csv(self, target_url: str, content: str):
        """Save tweet content into links.csv (content column)."""
        if not target_url or not content:
            return

        csv_path = Path(__file__).parent.parent / "database" / "links.csv"
        if not csv_path.exists():
            logger.warning(f"links.csv not found at {csv_path}")
            return

        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
        except Exception as e:
            logger.warning(f"Failed to read links.csv: {e}")
            return

        if 'content' not in fieldnames:
            fieldnames.append('content')

        normalized_target = self._normalize_x_url(target_url)
        updated = False
        for row in rows:
            # Check both 'url' (new schema) and 'target_url' (old schema)
            row_url = self._normalize_x_url(row.get('url') or row.get('target_url', ''))
            if row_url and row_url == normalized_target:
                if not row.get('content'):
                    row['content'] = content[:2000]
                    updated = True
                break

        if not updated:
            return

        tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
        try:
            with tmp_path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            tmp_path.replace(csv_path)
            logger.info(f"✅ Saved tweet content for {normalized_target}")
        except Exception as e:
            logger.warning(f"Failed to write links.csv: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _update_metrics_csv(self, target_url: str, metrics: Dict):
        """Update metrics (impressions, likes, comments, retweets) in links.csv."""
        if not target_url or not metrics:
            return

        csv_path = Path(__file__).parent.parent / "database" / "links.csv"
        if not csv_path.exists():
            logger.warning(f"links.csv not found at {csv_path}")
            return

        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
        except Exception as e:
            logger.warning(f"Failed to read links.csv: {e}")
            return

        normalized_target = self._normalize_x_url(target_url)
        updated = False
        for row in rows:
            row_url = self._normalize_x_url(row.get('url') or row.get('target_url', ''))
            if row_url and row_url == normalized_target:
                # Update metrics
                if metrics.get('impressions') is not None:
                    row['impressions'] = str(metrics['impressions'])
                if metrics.get('likes') is not None:
                    row['likes'] = str(metrics['likes'])
                if metrics.get('comments') is not None:
                    row['comments'] = str(metrics['comments'])
                if metrics.get('reposts') is not None:
                    row['retweets'] = str(metrics['reposts'])
                # Update synced_at timestamp
                row['synced_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return

        tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
        try:
            with tmp_path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            tmp_path.replace(csv_path)
            logger.info(f"✅ Updated metrics in CSV for {normalized_target}")
        except Exception as e:
            logger.warning(f"Failed to write links.csv: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

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
                # activity_url, target_url, task_id, notes
                row = [
                    date,                       # A: date
                    time_str,                   # B: time
                    activity['discord_user'],   # C: discord_user
                    activity['x_handle'],       # D: x_handle
                    activity_type,              # E: activity_type
                    activity_url,               # F: activity_url
                    target_url,                 # G: target_url
                    '',                         # H: task_id (empty for now)
                    notes                       # I: notes
                ]

                rows.append(row)

            # Write to monthly tab, columns A-I for X activities
            range_name = f"'{month_tab}'!A:I"

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

    def _get_existing_csv_activity_urls(self, csv_path: Path) -> set:
        """Get set of activity URLs already in CSV to prevent duplicates"""
        if not csv_path.exists():
            return set()

        existing_urls = set()
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    activity_url = row.get('activity_url', '').strip()
                    if activity_url:
                        existing_urls.add(activity_url)
            logger.debug(f"Found {len(existing_urls)} existing activities in CSV")
        except Exception as e:
            logger.warning(f"Could not read existing CSV data: {e}")
            return set()

        return existing_urls

    def write_activities_to_csv(self, activities: List[Dict], target_url: str):
        """Write activities to CSV file (append-only, no overwrites)"""
        if not activities:
            logger.info("No activities to write to CSV")
            return

        csv_path = Path(__file__).parent.parent / "database" / "x_activity_log.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Define CSV headers (excluding impressions and engagement)
        headers = [
            'date', 'time', 'discord_user', 'x_handle', 'activity_type',
            'activity_url', 'target_url', 'task_id', 'notes'
        ]

        # Check if file exists
        file_exists = csv_path.exists()

        # Get existing activity URLs to prevent duplicates
        existing_urls = self._get_existing_csv_activity_urls(csv_path)

        try:
            # IMPORTANT: Use 'a' (append) mode to never overwrite existing data
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write headers only if file is new
                if not file_exists:
                    writer.writerow(headers)
                    logger.info(f"Created new CSV file: {csv_path}")

                # Write activity rows
                rows_written = 0
                duplicates_skipped = 0

                for activity in activities:
                    activity_data = activity['activity']
                    timestamp = activity_data.get('timestamp', '')
                    date, time_str = self._parse_activity_timestamp(timestamp)
                    activity_type = activity_data.get('activity_type', 'comment')
                    activity_url = activity_data.get('url', '')

                    # Skip if this activity is already in the CSV
                    if activity_url in existing_urls:
                        duplicates_skipped += 1
                        logger.debug(f"Skipping duplicate CSV entry: {activity_url}")
                        continue

                    if activity_type in ('comment', 'quote'):
                        notes = activity_data.get('text', '')[:500]  # Limit text length
                    else:
                        notes = ''

                    row = [
                        date,                       # date
                        time_str,                   # time
                        activity['discord_user'],   # discord_user
                        activity['x_handle'],       # x_handle
                        activity_type,              # activity_type
                        activity_url,               # activity_url
                        target_url,                 # target_url
                        '',                         # task_id (empty for now)
                        notes                       # notes
                    ]

                    writer.writerow(row)
                    rows_written += 1

                if rows_written > 0:
                    logger.info(f"✅ Wrote {rows_written} new activities to CSV: {csv_path}")
                if duplicates_skipped > 0:
                    logger.info(f"⏭️  Skipped {duplicates_skipped} duplicate activities already in CSV")

        except Exception as e:
            logger.error(f"❌ Error writing to CSV: {str(e)}", exc_info=True)

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
                self.write_activities_to_csv(matched_activities, url)

            # Save tweet content locally (CSV) and update stats sheet
            if metrics.get('content'):
                self._update_task_content_csv(url, metrics.get('content'))

            metric_values = [
                metrics.get('impressions'),
                metrics.get('likes'),
                metrics.get('comments'),
                metrics.get('quotes'),
                metrics.get('reposts'),
            ]
            if metrics and any(value is not None for value in metric_values):
                self._update_metrics_csv(url, metrics)
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
