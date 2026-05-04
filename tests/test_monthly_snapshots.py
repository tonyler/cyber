"""Tests for scripts/monthly_views_snapshot.py and monthly_actions_snapshot.py"""
import csv
import sys
import pytest
from pathlib import Path
from datetime import date
from unittest.mock import patch

from helpers import write_csv


# ---------------------------------------------------------------------------
# monthly_views_snapshot
# ---------------------------------------------------------------------------

import monthly_views_snapshot as mvs


class TestAsInt:
    def test_plain_int(self):
        assert mvs._as_int("42") == 42

    def test_float_string(self):
        assert mvs._as_int("1.5") == 1

    def test_with_commas(self):
        assert mvs._as_int("1,234") == 1234

    def test_empty_string(self):
        assert mvs._as_int("") == 0

    def test_none(self):
        assert mvs._as_int(None) == 0

    def test_non_numeric(self):
        assert mvs._as_int("abc") == 0

    def test_zero(self):
        assert mvs._as_int("0") == 0


class TestRowToMonth:
    def test_year_month_field_used_first(self):
        assert mvs._row_to_month({"year_month": "2026-01"}) == "2026-01"

    def test_created_date_fallback(self):
        assert mvs._row_to_month({"created_date": "2026-02-15"}) == "2026-02"

    def test_date_fallback(self):
        assert mvs._row_to_month({"date": "2026-03-01"}) == "2026-03"

    def test_missing_fields_returns_none(self):
        assert mvs._row_to_month({}) is None

    def test_invalid_date_returns_none(self):
        assert mvs._row_to_month({"created_date": "not-a-date"}) is None

    def test_year_month_format_direct(self):
        assert mvs._row_to_month({"year_month": "2026-04"}) == "2026-04"


class TestMonthlyTotal:
    ROWS = [
        {"year_month": "2026-01", "impressions": "1000"},
        {"year_month": "2026-01", "impressions": "500"},
        {"year_month": "2026-02", "impressions": "200"},
        {"year_month": "2026-01", "impressions": ""},        # empty → 0
        {"year_month": "2026-01", "impressions": "invalid"}, # invalid → 0
    ]

    def test_sums_correct_month(self):
        total = mvs._monthly_total("2026-01", self.ROWS)
        assert total == 1500

    def test_different_month_not_included(self):
        total = mvs._monthly_total("2026-02", self.ROWS)
        assert total == 200

    def test_empty_impressions_treated_as_zero(self):
        rows = [{"year_month": "2026-03", "impressions": ""}]
        assert mvs._monthly_total("2026-03", rows) == 0

    def test_no_matching_rows(self):
        assert mvs._monthly_total("2099-12", self.ROWS) == 0


class TestLinksExistForMonth:
    ROWS = [
        {"year_month": "2026-01"},
        {"year_month": "2026-01"},
        {"year_month": "2026-02"},
    ]

    def test_count_for_existing_month(self):
        assert mvs._links_exist_for_month("2026-01", self.ROWS) == 2

    def test_count_for_other_month(self):
        assert mvs._links_exist_for_month("2026-02", self.ROWS) == 1

    def test_count_for_unknown_month(self):
        assert mvs._links_exist_for_month("2099-01", self.ROWS) == 0


class TestViewsSnapshotMain:
    def _make_links_csv(self, tmp_path, rows):
        path = tmp_path / "links.csv"
        write_csv(path, ["id", "platform", "url", "year_month", "impressions"], rows)
        return path

    def test_writes_snapshot_when_data_exists(self, tmp_path):
        self._make_links_csv(tmp_path, [
            {"id": "1", "platform": "x", "url": "https://x.com/1",
             "year_month": "2026-04", "impressions": "500"},
        ])
        views_dir = tmp_path / "monthly_views"
        views_dir.mkdir()

        with patch.object(mvs, "TASKS_FILE", tmp_path / "links.csv"), \
             patch.object(mvs, "VIEWS_DIR", views_dir), \
             patch("monthly_views_snapshot.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 24)
            mvs.main()

        snapshot = views_dir / "2026-04-views.csv"
        assert snapshot.exists()
        rows = list(csv.DictReader(snapshot.open()))
        assert len(rows) == 1
        assert rows[0]["total_views"] == "500"

    def test_skips_snapshot_when_all_impressions_zero(self, tmp_path):
        """Freshness guard: links exist but all impressions are zero → skip."""
        self._make_links_csv(tmp_path, [
            {"id": "1", "platform": "x", "url": "https://x.com/1",
             "year_month": "2026-04", "impressions": ""},
            {"id": "2", "platform": "x", "url": "https://x.com/2",
             "year_month": "2026-04", "impressions": "0"},
        ])
        views_dir = tmp_path / "monthly_views"
        views_dir.mkdir()

        with patch.object(mvs, "TASKS_FILE", tmp_path / "links.csv"), \
             patch.object(mvs, "VIEWS_DIR", views_dir), \
             patch("monthly_views_snapshot.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 24)
            mvs.main()

        snapshot = views_dir / "2026-04-views.csv"
        assert not snapshot.exists(), "Snapshot should NOT be written when all impressions are zero"

    def test_writes_snapshot_when_genuinely_zero(self, tmp_path):
        """Real zero: no links at all for the month → write zero snapshot (could be new month)."""
        self._make_links_csv(tmp_path, [
            {"id": "1", "platform": "x", "url": "https://x.com/1",
             "year_month": "2026-01", "impressions": "100"},
        ])
        views_dir = tmp_path / "monthly_views"
        views_dir.mkdir()

        with patch.object(mvs, "TASKS_FILE", tmp_path / "links.csv"), \
             patch.object(mvs, "VIEWS_DIR", views_dir), \
             patch("monthly_views_snapshot.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 24)
            mvs.main()

        # April has no links → total is genuinely 0 but no links exist → writes 0
        snapshot = views_dir / "2026-04-views.csv"
        assert snapshot.exists()
        rows = list(csv.DictReader(snapshot.open()))
        assert rows[0]["total_views"] == "0"


# ---------------------------------------------------------------------------
# monthly_actions_snapshot
# ---------------------------------------------------------------------------

import monthly_actions_snapshot as mas


class TestParseMonth:
    def test_iso_date(self):
        assert mas._parse_month("2026-01-15") == "2026-01"

    def test_year_month(self):
        assert mas._parse_month("2026-03") == "2026-03"

    def test_us_date_format(self):
        assert mas._parse_month("01/15/2026") == "2026-01"

    def test_invalid_returns_none(self):
        assert mas._parse_month("not-a-date") is None

    def test_empty_returns_none(self):
        assert mas._parse_month("") is None


class TestAggregateActions:
    def _make_activity_files(self, tmp_path, x_rows=None, reddit_rows=None):
        x_path = tmp_path / "x_activity_log.csv"
        reddit_path = tmp_path / "reddit_activity_log.csv"

        x_fields = ["date", "time", "discord_user", "x_handle", "activity_type", "activity_url", "target_url"]
        reddit_fields = ["date", "time", "discord_user", "reddit_username", "activity_type", "activity_url", "target_url"]

        if x_rows is not None:
            write_csv(x_path, x_fields, x_rows)
        if reddit_rows is not None:
            write_csv(reddit_path, reddit_fields, reddit_rows)

        return x_path, reddit_path

    def test_counts_x_comments(self, tmp_path):
        x_path, reddit_path = self._make_activity_files(tmp_path, x_rows=[
            {"date": "2026-04-01", "activity_type": "comment"},
            {"date": "2026-04-01", "activity_type": "comment"},
            {"date": "2026-04-02", "activity_type": "quote"},
        ])
        with patch.object(mas, "ACTIVITY_FILES", [
            (x_path, ("comment", "reply", "quote", "retweet", "repost")),
            (reddit_path, ("comment", "reply")),
        ]):
            counts = mas._aggregate_actions("2026-04")
        assert counts["2026-04-01"] == 2
        assert counts["2026-04-02"] == 1

    def test_filters_by_month(self, tmp_path):
        x_path, reddit_path = self._make_activity_files(tmp_path, x_rows=[
            {"date": "2026-04-01", "activity_type": "comment"},
            {"date": "2026-03-15", "activity_type": "comment"},
        ])
        with patch.object(mas, "ACTIVITY_FILES", [
            (x_path, ("comment",)),
            (reddit_path, ("comment",)),
        ]):
            counts = mas._aggregate_actions("2026-04")
        assert "2026-04-01" in counts
        assert "2026-03-15" not in counts

    def test_ignores_disallowed_activity_types(self, tmp_path):
        x_path, reddit_path = self._make_activity_files(tmp_path, x_rows=[
            {"date": "2026-04-01", "activity_type": "like"},   # not in allowed set
            {"date": "2026-04-01", "activity_type": "comment"},
        ])
        with patch.object(mas, "ACTIVITY_FILES", [
            (x_path, ("comment",)),
        ]):
            counts = mas._aggregate_actions("2026-04")
        assert counts.get("2026-04-01", 0) == 1

    def test_empty_files_returns_empty_dict(self, tmp_path):
        x_path, reddit_path = self._make_activity_files(tmp_path, x_rows=[], reddit_rows=[])
        with patch.object(mas, "ACTIVITY_FILES", [
            (x_path, ("comment",)),
            (reddit_path, ("comment",)),
        ]):
            counts = mas._aggregate_actions("2026-04")
        assert counts == {}


class TestActionsSnapshotMain:
    def test_skips_when_files_exist_but_no_data(self, tmp_path):
        """Freshness guard: log files exist but have no rows for current month."""
        x_path = tmp_path / "x_activity_log.csv"
        reddit_path = tmp_path / "reddit_activity_log.csv"
        # Files exist but only have January data
        write_csv(x_path, ["date", "activity_type"], [
            {"date": "2026-01-10", "activity_type": "comment"},
        ])
        write_csv(reddit_path, ["date", "activity_type"], [])

        actions_dir = tmp_path / "monthly_actions"
        actions_dir.mkdir()

        with patch.object(mas, "ACTIVITY_FILES", [
                (x_path, ("comment",)),
                (reddit_path, ("comment",)),
             ]), \
             patch.object(mas, "ACTIONS_DIR", actions_dir), \
             patch("monthly_actions_snapshot.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 24)
            mas.main()

        snapshot = actions_dir / "2026-04-actions.csv"
        assert not snapshot.exists(), "Should skip snapshot when scraper data is missing"

    def test_writes_snapshot_with_real_data(self, tmp_path):
        x_path = tmp_path / "x_activity_log.csv"
        reddit_path = tmp_path / "reddit_activity_log.csv"
        write_csv(x_path, ["date", "activity_type"], [
            {"date": "2026-04-10", "activity_type": "comment"},
            {"date": "2026-04-10", "activity_type": "repost"},
            {"date": "2026-04-11", "activity_type": "comment"},
        ])
        write_csv(reddit_path, ["date", "activity_type"], [
            {"date": "2026-04-10", "activity_type": "comment"},
        ])

        actions_dir = tmp_path / "monthly_actions"
        actions_dir.mkdir()

        with patch.object(mas, "ACTIVITY_FILES", [
                (x_path, ("comment", "repost")),
                (reddit_path, ("comment",)),
             ]), \
             patch.object(mas, "ACTIONS_DIR", actions_dir), \
             patch("monthly_actions_snapshot.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 24)
            mas.main()

        snapshot = actions_dir / "2026-04-actions.csv"
        assert snapshot.exists()
        rows = list(csv.DictReader(snapshot.open()))
        totals = {r["date"]: int(r["total_actions"]) for r in rows}
        assert totals["2026-04-10"] == 3   # 2 x + 1 reddit
        assert totals["2026-04-11"] == 4   # cumulative: 3 + 1
