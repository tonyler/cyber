"""Tests for scrapers/reddit_scraper.py — pure logic methods only (no browser/sheets)."""
import pytest
from unittest.mock import MagicMock, patch


def make_reddit_scraper(tmp_path):
    with patch("base_scraper.sync_playwright"), \
         patch("base_scraper.MembersDBService"), \
         patch("base_scraper.LinksDBService"), \
         patch("reddit_scraper.service_account"), \
         patch("reddit_scraper.build"), \
         patch("reddit_scraper.SheetStatsUpdater"):
        from reddit_scraper import RedditScraper

        scraper = RedditScraper.__new__(RedditScraper)
        scraper.active_members = {}
        scraper.x_handles = set()
        scraper.reddit_usernames = set()
        scraper.sheet_config = {"sync": {"month_tab_format": "MM/YY"}}
        scraper.verbose_metrics = False
        scraper.playwright = None
        scraper.browser = None
        scraper.context = None
        scraper.page = None
        scraper.activity_sheet_id = "fake_id"
        scraper.credentials_file = str(tmp_path / "creds.json")
        scraper.sheets_service = MagicMock()
        scraper.stats_updater = None
        scraper.stats_sheet_id = None
        return scraper


class TestToOldReddit:
    def _convert(self, url, tmp_path):
        s = make_reddit_scraper(tmp_path)
        return s._to_old_reddit(url)

    def test_www_to_old(self, tmp_path):
        assert self._convert("https://www.reddit.com/r/test/comments/abc/", tmp_path) \
               == "https://old.reddit.com/r/test/comments/abc/"

    def test_bare_reddit_to_old(self, tmp_path):
        assert self._convert("https://reddit.com/r/test/", tmp_path) \
               == "https://old.reddit.com/r/test/"

    def test_already_old_unchanged(self, tmp_path):
        url = "https://old.reddit.com/r/test/comments/abc/"
        assert self._convert(url, tmp_path) == url

    def test_no_domain_prefix(self, tmp_path):
        # URL without www or old — should still convert
        result = self._convert("https://reddit.com/r/foo/", tmp_path)
        assert "old.reddit.com" in result


class TestUrlsMatchReddit:
    def _match(self, url1, url2, tmp_path):
        s = make_reddit_scraper(tmp_path)
        return s._urls_match(url1, url2)

    def test_same_post_id_matches(self, tmp_path):
        u1 = "https://www.reddit.com/r/test/comments/abc123/some_title/"
        u2 = "https://old.reddit.com/r/test/comments/abc123/other_title/"
        assert self._match(u1, u2, tmp_path) is True

    def test_different_post_ids_no_match(self, tmp_path):
        u1 = "https://reddit.com/r/test/comments/abc123/title/"
        u2 = "https://reddit.com/r/test/comments/xyz999/title/"
        assert self._match(u1, u2, tmp_path) is False

    def test_www_vs_old_same_post(self, tmp_path):
        u1 = "https://www.reddit.com/r/crypto/comments/def456/post/"
        u2 = "https://old.reddit.com/r/crypto/comments/def456/post/"
        assert self._match(u1, u2, tmp_path) is True

    def test_trailing_slash_ignored(self, tmp_path):
        u1 = "https://reddit.com/r/test/comments/ghi789/title"
        u2 = "https://reddit.com/r/test/comments/ghi789/title/"
        assert self._match(u1, u2, tmp_path) is True

    def test_no_comments_path_falls_back_to_string_compare(self, tmp_path):
        # Share-style URLs without /comments/ — falls back to basic string comparison
        u1 = "https://reddit.com/r/test/s/abc123"
        u2 = "https://reddit.com/r/test/s/abc123"
        assert self._match(u1, u2, tmp_path) is True


class TestMatchCommentsToMembers:
    def test_matches_registered_reddit_user(self, tmp_path):
        s = make_reddit_scraper(tmp_path)
        s.active_members = {
            "alice": {"discord_user": "alice", "x_handle": "", "reddit_username": "alice_r"}
        }
        comments = [{"username": "alice_r", "text": "great post", "url": "https://old.reddit.com/r/t/c/1", "score": 5}]
        matched = s.match_comments_to_members(comments)
        assert len(matched) == 1
        assert matched[0]["discord_user"] == "alice"

    def test_unregistered_user_not_matched(self, tmp_path):
        s = make_reddit_scraper(tmp_path)
        s.active_members = {}
        matched = s.match_comments_to_members([{"username": "random"}])
        assert matched == []

    def test_deleted_user_not_matched(self, tmp_path):
        s = make_reddit_scraper(tmp_path)
        s.active_members = {"alice": {"discord_user": "alice", "reddit_username": "alice_r"}}
        matched = s.match_comments_to_members([{"username": "[deleted]"}])
        assert matched == []

    def test_empty_list_returns_empty(self, tmp_path):
        s = make_reddit_scraper(tmp_path)
        assert s.match_comments_to_members([]) == []


class TestExtractCommentData:
    def _make_element(self, username="testuser", text="hello", score="10", permalink="/r/test/c/1"):
        """Build a mock Playwright element for a Reddit comment."""
        def make_loc(content):
            loc = MagicMock()
            loc.count.return_value = 1
            loc.text_content.return_value = content
            loc.get_attribute.return_value = permalink if "bylink" in str(loc) else None
            return loc

        element = MagicMock()

        author_loc = MagicMock()
        author_loc.count.return_value = 1
        author_loc.text_content.return_value = username

        text_loc = MagicMock()
        text_loc.count.return_value = 1
        text_loc.text_content.return_value = text

        score_loc = MagicMock()
        score_loc.count.return_value = 1
        score_loc.text_content.return_value = score

        permalink_loc = MagicMock()
        permalink_loc.count.return_value = 1
        permalink_loc.get_attribute.return_value = permalink

        def locator_side_effect(selector):
            loc = MagicMock()
            loc.first = author_loc if ".author" in selector else (
                text_loc if ".usertext-body" in selector else (
                    score_loc if ".score" in selector else permalink_loc
                )
            )
            return loc

        element.locator.side_effect = locator_side_effect
        return element

    def test_valid_comment_extracted(self, tmp_path):
        s = make_reddit_scraper(tmp_path)
        el = self._make_element(username="alice_r", text="nice post", score="5")
        # Patch the permalink locator
        permalink_loc = MagicMock()
        permalink_loc.count.return_value = 1
        permalink_loc.get_attribute.return_value = "/r/test/comments/abc/post/xyz/"

        def loc_side_effect(selector):
            loc = MagicMock()
            if ".author" in selector:
                loc.first = MagicMock(count=lambda: 1, text_content=lambda: "alice_r")
            elif ".usertext-body" in selector:
                loc.first = MagicMock(count=lambda: 1, text_content=lambda: "nice post")
            elif ".score" in selector:
                loc.first = MagicMock(count=lambda: 1, text_content=lambda: "5 points")
            elif "bylink" in selector:
                m = MagicMock()
                m.count.return_value = 1
                m.get_attribute.return_value = "/r/test/comments/abc/post/xyz/"
                loc.first = m
            return loc

        el.locator.side_effect = loc_side_effect
        result = s._extract_comment_data(el, "https://reddit.com/r/test/comments/abc/post/")
        assert result["username"] == "alice_r"
        assert result["text"] == "nice post"

    def test_deleted_user_returns_none(self, tmp_path):
        s = make_reddit_scraper(tmp_path)
        el = MagicMock()

        def loc_side_effect(selector):
            loc = MagicMock()
            if ".author" in selector:
                loc.first = MagicMock(count=lambda: 1, text_content=lambda: "[deleted]")
            else:
                loc.first = MagicMock(count=lambda: 0, text_content=lambda: "")
            return loc

        el.locator.side_effect = loc_side_effect
        result = s._extract_comment_data(el, "https://reddit.com/r/test/")
        assert result is None
