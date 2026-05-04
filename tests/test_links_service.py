"""Tests for shared/links_service.py"""
import pytest
from pathlib import Path

from links_service import LinksDBService
from helpers import write_csv, LINKS_FIELDNAMES


@pytest.fixture
def svc(tmp_path):
    path = tmp_path / "links.csv"
    write_csv(path, LINKS_FIELDNAMES, [
        {"id": "1", "platform": "x",      "url": "https://x.com/i/status/111",
         "author": "alice", "year_month": "2026-01", "date": "2026-01-10"},
        {"id": "2", "platform": "reddit", "url": "https://reddit.com/r/t/comments/abc/p",
         "author": "bob",   "year_month": "2026-01", "date": "2026-01-11"},
        {"id": "3", "platform": "x",      "url": "https://x.com/i/status/222",
         "author": "carol", "year_month": "2026-02", "date": "2026-02-05"},
    ])
    return LinksDBService(str(path))


class TestGetAllLinks:
    def test_returns_all_rows(self, svc):
        assert len(svc.get_all_links()) == 3

    def test_missing_file_returns_empty(self, tmp_path):
        s = LinksDBService(str(tmp_path / "nope.csv"))
        assert s.get_all_links() == []


class TestGetLinksForMonth:
    def test_filters_correctly(self, svc):
        links = svc.get_links_for_month("2026-01")
        assert len(links) == 2
        assert all(l["year_month"] == "2026-01" for l in links)

    def test_unknown_month_returns_empty(self, svc):
        assert svc.get_links_for_month("2099-12") == []


class TestGetLinksForMonthAndPlatform:
    def test_x_only(self, svc):
        links = svc.get_links_for_month_and_platform("2026-01", "x")
        assert len(links) == 1
        assert links[0]["platform"] == "x"

    def test_reddit_only(self, svc):
        links = svc.get_links_for_month_and_platform("2026-01", "reddit")
        assert len(links) == 1
        assert links[0]["platform"] == "reddit"

    def test_case_insensitive_platform(self, svc):
        links = svc.get_links_for_month_and_platform("2026-01", "X")
        assert len(links) == 1

    def test_no_match_returns_empty(self, svc):
        assert svc.get_links_for_month_and_platform("2026-01", "tiktok") == []


class TestGetLinkByUrl:
    def test_finds_existing_url(self, svc):
        link = svc.get_link_by_url("https://x.com/i/status/111")
        assert link["author"] == "alice"

    def test_missing_url_returns_empty_dict(self, svc):
        assert svc.get_link_by_url("https://nowhere.com") == {}
