import csv
import os
import sys
import re
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

project_root = Path(__file__).parent.parent
shared_dir = project_root / "shared"
sys.path.insert(0, str(shared_dir))

from logger_config import setup_logger
from members_service import MembersDBService
from links_service import LinksDBService

logger = setup_logger(__name__)

class BaseScraper:
    def __init__(self, members_db_path: str, links_db_path: str, headless: bool = True):
        self.members_db_path = members_db_path
        self.links_db_path = links_db_path
        self.headless = headless

        self.members_db = MembersDBService(members_db_path)
        self.links_db = LinksDBService(links_db_path)

        self.active_members = {}
        self.x_handles = set()
        self.reddit_usernames = set()
        self._load_active_members()

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        logger.info(f"{self.__class__.__name__} initialized")

    def _init_browser(self):
        """Initialize playwright browser with silent/headless mode"""
        if self.playwright is None:
            self.playwright = sync_playwright().start()

        if self.browser is None:
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]

            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=browser_args
            )

        if self.context is None:
            # Use Chrome Android UA — mobile viewport, Chromium UA.
            # iPhone/Safari UA causes X to serve a layout with no article elements.
            self.context = self.browser.new_context(
                viewport={'width': 390, 'height': 844},
                user_agent=(
                    'Mozilla/5.0 (Linux; Android 14; Pixel 8) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Mobile Safari/537.36'
                ),
                is_mobile=True,
                has_touch=True,
                device_scale_factor=2.0,
                ignore_https_errors=True,
                locale='en-US',
            )

        if self.page is None:
            self.page = self.context.new_page()

        logger.info("Browser initialized successfully")

    def _close_browser(self):
        """Close browser and cleanup"""
        try:
            if self.page:
                self.page.close()
                self.page = None
            if self.context:
                self.context.close()
                self.context = None
            if self.browser:
                self.browser.close()
                self.browser = None
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

    def _restart_browser(self):
        """Restart the browser"""
        logger.info("Restarting browser...")
        self._close_browser()
        self._init_browser()

    def _safe_get(self, url: str, retries: int = 1, delay_seconds: float = 2.0) -> None:
        """Navigate to a URL with retries."""
        import time
        for attempt in range(retries + 1):
            try:
                if self.page is None:
                    self._init_browser()
                self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
                # X is a React SPA — wait for article elements to render before returning
                if 'x.com' in url or 'twitter.com' in url:
                    try:
                        self.page.wait_for_selector('article', timeout=10000)
                    except Exception:
                        pass  # Proceed anyway; caller handles empty results
                return
            except Exception as exc:
                if attempt < retries:
                    logger.warning(f"Error loading {url}; retrying (attempt {attempt + 1}/{retries + 1}): {exc}")
                    self._restart_browser()
                    time.sleep(delay_seconds)
                    continue
                raise

    def _run_with_timeout(self, seconds: int, func, *args, **kwargs):
        if seconds <= 0:
            return func(*args, **kwargs)

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Operation timed out after {seconds} seconds")

        previous_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(seconds)
        try:
            return func(*args, **kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _load_active_members(self):
        members = self.members_db.get_active_members()
        for member in members:
            discord_user = member.get('discord_user')
            x_handle = member.get('x_handle', '').strip().lower()
            reddit_username = member.get('reddit_username', '').strip().lower()

            if discord_user:
                self.active_members[discord_user] = member
                if x_handle:
                    self.x_handles.add(x_handle)
                if reddit_username:
                    self.reddit_usernames.add(reddit_username)

        logger.info(f"Loaded {len(self.active_members)} active members")

    def find_member_by_x_handle(self, x_handle: str) -> Dict:
        """Find member by X handle (case-insensitive)"""
        if not x_handle:
            return None
        x_handle = x_handle.strip().lower()
        for member in self.active_members.values():
            member_handle = member.get('x_handle', '').strip().lower()
            if member_handle == x_handle:
                return member
        return None

    def find_member_by_reddit_username(self, reddit_username: str) -> Dict:
        """Find member by Reddit username (case-insensitive)"""
        if not reddit_username:
            return None
        reddit_username = reddit_username.strip().lower()
        for member in self.active_members.values():
            member_username = member.get('reddit_username', '').strip().lower()
            if member_username == reddit_username:
                return member
        return None

    @staticmethod
    def parse_count(text: str) -> int:
        """Parse count from text like '1.2K', '3M', '42', etc."""
        if not text:
            return 0
        text = str(text).strip().upper()
        # Remove commas
        text = text.replace(',', '')
        # Extract number and multiplier
        match = re.match(r'([\d\.]+)([KMB])?', text)
        if not match:
            return 0
        number = float(match.group(1))
        multiplier = match.group(2)
        if multiplier == 'K':
            return int(number * 1000)
        elif multiplier == 'M':
            return int(number * 1000000)
        elif multiplier == 'B':
            return int(number * 1000000000)
        return int(number)

    def _get_current_month_tab(self) -> str:
        """Get current month tab name based on config format (e.g., '01/26')."""
        now = datetime.now()
        month_tab_format = self.sheet_config.get('sync', {}).get('month_tab_format', 'MM/YY')
        if month_tab_format == 'MM/YYYY':
            return now.strftime('%m/%Y')
        return now.strftime('%m/%y')

    def _get_existing_csv_activity_urls(self, csv_path: Path) -> set:
        """Return set of activity_url values already in a CSV to prevent duplicates."""
        if not csv_path.exists():
            return set()
        existing = set()
        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    url = row.get('activity_url', '').strip()
                    if url:
                        existing.add(url)
        except Exception as e:
            logger.warning(f"Could not read existing CSV data: {e}")
        return existing

    def _update_links_csv_row(self, target_url: str, updates: dict):
        """Update specific columns for a matching row in links.csv using tmp-file safety."""
        csv_path = Path(__file__).parent.parent / "database" / "links.csv"
        if not csv_path.exists():
            logger.warning("links.csv not found")
            return

        try:
            with csv_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                rows = list(reader)
        except Exception as e:
            logger.warning(f"Failed to read links.csv: {e}")
            return

        updated = False
        for row in rows:
            row_url = (row.get('url') or row.get('target_url', '')).strip()
            if self._urls_match(row_url, target_url):
                for key, value in updates.items():
                    if key not in fieldnames:
                        fieldnames.append(key)
                    if value is not None:
                        row[key] = str(value)
                row['synced_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return

        tmp_path = csv_path.with_suffix(csv_path.suffix + '.tmp')
        try:
            with tmp_path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            tmp_path.replace(csv_path)
            logger.info(f"Updated links.csv for {target_url}")
        except Exception as e:
            logger.warning(f"Failed to write links.csv: {e}")
            tmp_path.unlink(missing_ok=True)

    def _urls_match(self, url1: str, url2: str) -> bool:
        """Check if two URLs refer to the same resource (platform-agnostic base)."""
        return url1.rstrip('/').lower() == url2.rstrip('/').lower()

    def __enter__(self):
        """Context manager entry"""
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self._close_browser()
        return False
