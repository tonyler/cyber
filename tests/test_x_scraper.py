"""Tests for scrapers/x_scraper.py — pure logic methods only (no browser/sheets)."""
import pytest
from unittest.mock import MagicMock, patch


def make_x_scraper(tmp_path):
    """Build XScraper with all external deps mocked."""
    with patch("base_scraper.sync_playwright"), \
         patch("base_scraper.MembersDBService"), \
         patch("base_scraper.LinksDBService"), \
         patch("x_scraper.service_account"), \
         patch("x_scraper.build"), \
         patch("x_scraper.SheetStatsUpdater"):
        from x_scraper import XScraper

        scraper = XScraper.__new__(XScraper)
        scraper.active_members = {}
        scraper.x_handles = set()
        scraper.reddit_usernames = set()
        scraper.sheet_config = {"sync": {"month_tab_format": "MM/YY"}}
        scraper.verbose_metrics = False
        scraper.playwright = None
        scraper.browser = None
        scraper.context = None
        scraper.page = None
        scraper.session_file = str(tmp_path / "x_session.json")
        scraper.activity_sheet_id = "fake_id"
        scraper.credentials_file = str(tmp_path / "creds.json")
        scraper.sheets_service = MagicMock()
        scraper.stats_updater = None
        scraper.stats_sheet_id = None
        return scraper


class TestNormalizeXUrl:
    def setup_method(self):
        with patch("base_scraper.sync_playwright"), \
             patch("base_scraper.MembersDBService"), \
             patch("base_scraper.LinksDBService"), \
             patch("x_scraper.service_account"), \
             patch("x_scraper.build"), \
             patch("x_scraper.SheetStatsUpdater"):
            from x_scraper import XScraper
            self.scraper_class = XScraper

    def _norm(self, url):
        from x_scraper import XScraper
        return XScraper._normalize_x_url(MagicMock(), url)

    def test_status_url_normalized(self):
        result = self._norm("https://x.com/user/status/12345")
        assert result == "https://x.com/i/status/12345"

    def test_i_status_url_unchanged(self):
        result = self._norm("https://x.com/i/status/12345")
        assert result == "https://x.com/i/status/12345"

    def test_twitter_url_normalized(self):
        result = self._norm("https://twitter.com/user/status/99999")
        assert result == "https://x.com/i/status/99999"

    def test_bare_id_becomes_url(self):
        result = self._norm("12345678")
        assert result == "https://x.com/i/status/12345678"

    def test_url_without_protocol_gets_https(self):
        result = self._norm("x.com/user/status/111")
        # no /status match, falls through to https:// prefix
        assert result.startswith("https://")

    def test_none_returns_none(self):
        result = self._norm(None)
        assert result is None

    def test_empty_returns_empty(self):
        result = self._norm("")
        assert result == ""


class TestParseActivityTimestamp:
    def _parse(self, ts):
        with patch("base_scraper.sync_playwright"), \
             patch("base_scraper.MembersDBService"), \
             patch("base_scraper.LinksDBService"), \
             patch("x_scraper.service_account"), \
             patch("x_scraper.build"), \
             patch("x_scraper.SheetStatsUpdater"):
            from x_scraper import XScraper
            return XScraper._parse_activity_timestamp(MagicMock(), ts)

    def test_iso_timestamp(self):
        date, time = self._parse("2026-01-15T10:30:00Z")
        assert date == "2026-01-15"
        assert time == "10:30:00"

    def test_iso_with_offset(self):
        date, time = self._parse("2026-03-20T14:00:00+00:00")
        assert date == "2026-03-20"
        assert time == "14:00:00"

    def test_none_returns_today(self):
        from datetime import datetime
        date, time = self._parse(None)
        today = datetime.now().strftime("%Y-%m-%d")
        assert date == today

    def test_invalid_string_returns_today(self):
        from datetime import datetime
        date, time = self._parse("not-a-date")
        today = datetime.now().strftime("%Y-%m-%d")
        assert date == today


class TestBuildActivityUrl:
    def _build(self, url, suffix):
        with patch("base_scraper.sync_playwright"), \
             patch("base_scraper.MembersDBService"), \
             patch("base_scraper.LinksDBService"), \
             patch("x_scraper.service_account"), \
             patch("x_scraper.build"), \
             patch("x_scraper.SheetStatsUpdater"):
            from x_scraper import XScraper
            return XScraper._build_activity_url(MagicMock(), url, suffix)

    def test_quotes_url(self):
        url = self._build("https://x.com/i/status/123", "quotes")
        assert url == "https://x.com/i/status/123/quotes"

    def test_retweets_url(self):
        url = self._build("https://x.com/i/status/123", "retweets")
        assert url == "https://x.com/i/status/123/retweets"

    def test_strips_query_params(self):
        url = self._build("https://x.com/i/status/123?s=20", "quotes")
        assert url == "https://x.com/i/status/123/quotes"

    def test_strips_trailing_slash(self):
        url = self._build("https://x.com/i/status/123/", "quotes")
        assert url == "https://x.com/i/status/123/quotes"


class TestMatchActivitiesToMembers:
    def test_matches_registered_member(self, tmp_path):
        s = make_x_scraper(tmp_path)
        s.active_members = {
            "alice": {"discord_user": "alice", "x_handle": "alice_x", "reddit_username": ""}
        }
        activities = [
            {"username": "alice_x", "activity_type": "comment", "url": "https://x.com/a/1", "text": "hi"}
        ]
        matched = s.match_activities_to_members(activities)
        assert len(matched) == 1
        assert matched[0]["discord_user"] == "alice"

    def test_unregistered_user_not_matched(self, tmp_path):
        s = make_x_scraper(tmp_path)
        s.active_members = {}
        activities = [{"username": "random_user", "activity_type": "comment"}]
        matched = s.match_activities_to_members(activities)
        assert matched == []

    def test_empty_activities_returns_empty(self, tmp_path):
        s = make_x_scraper(tmp_path)
        assert s.match_activities_to_members([]) == []
