"""Tests for shared/members_service.py"""
import csv
import pytest
from pathlib import Path

from members_service import MembersDBService
from helpers import write_csv, MEMBERS_FIELDNAMES, LINKS_FIELDNAMES, X_ACTIVITY_FIELDNAMES, REDDIT_ACTIVITY_FIELDNAMES


@pytest.fixture
def db(tmp_path):
    members_path = tmp_path / "members.csv"
    write_csv(members_path, MEMBERS_FIELDNAMES, [
        {"discord_user": "alice", "x_handle": "alice_x", "reddit_username": "alice_r", "status": "active"},
        {"discord_user": "bob",   "x_handle": "bob_x",   "reddit_username": "bob_r",   "status": "inactive"},
        {"discord_user": "carol", "x_handle": "Carol_X", "reddit_username": "carol_r", "status": "active"},
    ])
    return MembersDBService(str(members_path))


@pytest.fixture
def db_with_links(tmp_path):
    members_path = tmp_path / "members.csv"
    write_csv(members_path, MEMBERS_FIELDNAMES, [
        {"discord_user": "alice", "x_handle": "alice_x", "reddit_username": "alice_r", "status": "active"},
    ])

    links_path = tmp_path / "links.csv"
    write_csv(links_path, LINKS_FIELDNAMES, [
        {"id": "1", "platform": "x",      "url": "https://x.com/i/status/111", "author": "alice",
         "year_month": "2026-01", "date": "2026-01-10", "impressions": "1000"},
        {"id": "2", "platform": "reddit", "url": "https://reddit.com/r/t/comments/abc/p", "author": "alice",
         "year_month": "2026-01", "date": "2026-01-11", "impressions": "200"},
        {"id": "3", "platform": "x",      "url": "https://x.com/i/status/222", "author": "alice",
         "year_month": "2026-02", "date": "2026-02-01", "impressions": ""},
    ])

    x_act_path = tmp_path / "x_activity_log.csv"
    write_csv(x_act_path, X_ACTIVITY_FIELDNAMES, [
        {"date": "2026-01-10", "time": "10:00:00", "discord_user": "alice", "x_handle": "alice_x",
         "activity_type": "comment", "activity_url": "https://x.com/alice/status/999",
         "target_url": "https://x.com/i/status/111"},
        {"date": "2026-01-10", "time": "11:00:00", "discord_user": "alice", "x_handle": "alice_x",
         "activity_type": "repost",  "activity_url": "https://x.com/alice",
         "target_url": "https://x.com/i/status/111"},
    ])

    reddit_act_path = tmp_path / "reddit_activity_log.csv"
    write_csv(reddit_act_path, REDDIT_ACTIVITY_FIELDNAMES, [
        {"date": "2026-01-11", "time": "09:00:00", "discord_user": "alice", "reddit_username": "alice_r",
         "activity_type": "comment", "activity_url": "https://old.reddit.com/r/t/comments/abc/p/comment/xyz",
         "target_url": "https://reddit.com/r/t/comments/abc/p"},
    ])

    return MembersDBService(str(members_path))


class TestReadCsv:
    def test_missing_file_returns_empty(self, tmp_path):
        svc = MembersDBService(str(tmp_path / "nope.csv"))
        assert svc.get_all_members() == []

    def test_reads_all_rows(self, db):
        members = db.get_all_members()
        assert len(members) == 3
        assert members[0]["discord_user"] == "alice"


class TestGetActiveMembers:
    def test_filters_inactive(self, db):
        active = db.get_active_members()
        names = [m["discord_user"] for m in active]
        assert "alice" in names
        assert "carol" in names
        assert "bob" not in names


class TestGetMemberByXHandle:
    def test_exact_match(self, db):
        m = db.get_member_by_x_handle("alice_x")
        assert m["discord_user"] == "alice"

    def test_case_insensitive(self, db):
        m = db.get_member_by_x_handle("CAROL_X")
        assert m["discord_user"] == "carol"

    def test_strips_at_prefix(self, db):
        m = db.get_member_by_x_handle("@alice_x")
        assert m["discord_user"] == "alice"

    def test_not_found_returns_none(self, db):
        assert db.get_member_by_x_handle("nobody") is None

    def test_empty_returns_none(self, db):
        assert db.get_member_by_x_handle("") is None


class TestGetMemberByRedditUsername:
    def test_exact_match(self, db):
        m = db.get_member_by_reddit_username("alice_r")
        assert m["discord_user"] == "alice"

    def test_case_insensitive(self, db):
        m = db.get_member_by_reddit_username("ALICE_R")
        assert m["discord_user"] == "alice"

    def test_strips_u_prefix(self, db):
        m = db.get_member_by_reddit_username("u/alice_r")
        assert m["discord_user"] == "alice"

    def test_not_found_returns_none(self, db):
        assert db.get_member_by_reddit_username("nobody") is None

    def test_empty_returns_none(self, db):
        assert db.get_member_by_reddit_username("") is None


class TestGetTasksForMonth:
    def test_returns_all_when_no_filter(self, db_with_links):
        tasks = db_with_links.get_tasks_for_month("")
        assert len(tasks) == 3

    def test_filters_by_month(self, db_with_links):
        tasks = db_with_links.get_tasks_for_month("2026-01")
        assert len(tasks) == 2
        assert all(t["year_month"] == "2026-01" for t in tasks)

    def test_normalizes_url_to_target_url(self, db_with_links):
        tasks = db_with_links.get_tasks_for_month("2026-01")
        assert all("target_url" in t for t in tasks)

    def test_default_task_type_is_content(self, db_with_links):
        tasks = db_with_links.get_tasks_for_month("2026-01")
        assert all(t.get("task_type") == "content" for t in tasks)

    def test_normalizes_date_to_created_date(self, db_with_links):
        tasks = db_with_links.get_tasks_for_month("2026-01")
        assert all(t.get("created_date") for t in tasks)

    def test_no_results_for_unknown_month(self, db_with_links):
        assert db_with_links.get_tasks_for_month("2099-12") == []

    def test_available_task_months_sorted_desc(self, db_with_links):
        assert db_with_links.get_available_task_months() == ["2026-02", "2026-01"]


class TestGetXActivitiesByMember:
    def test_returns_activities_for_member(self, db_with_links):
        acts = db_with_links.get_x_activities_by_member("alice")
        assert len(acts) == 2

    def test_case_insensitive_user(self, db_with_links):
        acts = db_with_links.get_x_activities_by_member("ALICE")
        assert len(acts) == 2

    def test_empty_user_returns_empty(self, db_with_links):
        assert db_with_links.get_x_activities_by_member("") == []

    def test_unknown_user_returns_empty(self, db_with_links):
        assert db_with_links.get_x_activities_by_member("nobody") == []

    def test_filters_by_month(self, db_with_links):
        acts = db_with_links.get_x_activities_by_member("alice", "2026-01")
        assert len(acts) == 2
        assert db_with_links.get_x_activities_by_member("alice", "2026-02") == []


class TestGetXActivityUrlsForTarget:
    def test_returns_urls_for_target(self, db_with_links):
        urls = db_with_links.get_x_activity_urls_for_target("https://x.com/i/status/111")
        assert "https://x.com/alice/status/999" in urls
        assert "https://x.com/alice" in urls

    def test_wrong_target_returns_empty(self, db_with_links):
        urls = db_with_links.get_x_activity_urls_for_target("https://x.com/i/status/999")
        assert urls == set()


class TestGetCombinedActivityHistory:
    def test_merges_x_and_reddit(self, db_with_links):
        acts = db_with_links.get_combined_activity_history()
        platforms = {a["platform"] for a in acts}
        assert "x" in platforms
        assert "reddit" in platforms

    def test_filters_by_month(self, db_with_links):
        acts = db_with_links.get_combined_activity_history("2026-01")
        assert all(a["date"].startswith("2026-01") for a in acts)

    def test_sorted_descending(self, db_with_links):
        acts = db_with_links.get_combined_activity_history()
        dates = [f"{a['date']} {a['time']}" for a in acts]
        assert dates == sorted(dates, reverse=True)

    def test_adds_platform_specific_username_labels(self, db_with_links):
        acts = db_with_links.get_combined_activity_history()
        labels = {a["platform"]: a["username_label"] for a in acts}
        assert labels["x"] == "@alice_x"
        assert labels["reddit"] == "u/alice_r"

    def test_available_activity_months_sorted_desc(self, db_with_links):
        assert db_with_links.get_available_activity_months() == ["2026-01"]


class TestGetMemberContributionStats:
    def test_returns_lifetime_totals(self, db_with_links):
        stats = db_with_links.get_member_contribution_stats("alice")
        assert stats == {
            "x_comments": 1,
            "x_quotes": 0,
            "x_retweets": 1,
            "reddit_comments": 1,
            "total_contributions": 3,
        }

    def test_returns_month_scoped_totals(self, db_with_links):
        stats = db_with_links.get_member_contribution_stats("alice", "2026-02")
        assert stats["total_contributions"] == 0


class TestUpsertMember:
    def test_insert_new_member(self, db, tmp_path):
        new = {"discord_user": "dave", "x_handle": "dave_x", "status": "active"}
        result = db.upsert_member(new)
        assert result is True
        members = db.get_all_members()
        assert any(m["discord_user"] == "dave" for m in members)

    def test_update_existing_member(self, db):
        update = {"discord_user": "alice", "x_handle": "alice_new_x", "status": "active"}
        db.upsert_member(update)
        m = db.get_member_by_x_handle("alice_new_x")
        assert m is not None

    def test_no_discord_user_returns_false(self, db):
        assert db.upsert_member({"x_handle": "orphan"}) is False


class TestUpsertTask:
    def test_insert_new_task(self, db_with_links):
        task = {"url": "https://x.com/i/status/999", "platform": "x", "year_month": "2026-03"}
        result = db_with_links.upsert_task(task)
        assert result is True
        tasks = db_with_links.get_tasks_for_month("2026-03")
        assert len(tasks) == 1

    def test_update_existing_task(self, db_with_links):
        # Include year_month so the upsert doesn't clear it
        task = {"url": "https://x.com/i/status/111", "impressions": "9999",
                "platform": "x", "year_month": "2026-01"}
        db_with_links.upsert_task(task)
        tasks = db_with_links.get_tasks_for_month("2026-01")
        updated = next(t for t in tasks if t["url"] == "https://x.com/i/status/111")
        assert updated["impressions"] == "9999"

    def test_no_url_returns_false(self, db_with_links):
        assert db_with_links.upsert_task({"platform": "x"}) is False


class TestInsertXActivitiesBatch:
    def test_inserts_new_activities(self, db_with_links):
        new_acts = [
            {"date": "2026-01-12", "time": "12:00:00", "discord_user": "alice",
             "x_handle": "alice_x", "activity_type": "quote",
             "activity_url": "https://x.com/alice/status/777",
             "target_url": "https://x.com/i/status/111"},
        ]
        count = db_with_links.insert_x_activities_batch(new_acts)
        assert count == 1

    def test_skips_duplicates(self, db_with_links):
        duplicate = [
            {"activity_url": "https://x.com/alice/status/999", "discord_user": "alice",
             "x_handle": "alice_x", "activity_type": "comment",
             "target_url": "https://x.com/i/status/111"},
        ]
        count = db_with_links.insert_x_activities_batch(duplicate)
        assert count == 0

    def test_empty_list_returns_zero(self, db_with_links):
        assert db_with_links.insert_x_activities_batch([]) == 0


class TestDeleteTasksForMonth:
    def test_deletes_correct_month(self, db_with_links):
        deleted = db_with_links.delete_tasks_for_month("2026-01")
        assert deleted == 2
        assert db_with_links.get_tasks_for_month("2026-01") == []

    def test_leaves_other_months_intact(self, db_with_links):
        db_with_links.delete_tasks_for_month("2026-01")
        assert len(db_with_links.get_tasks_for_month("2026-02")) == 1

    def test_empty_month_returns_zero(self, db_with_links):
        assert db_with_links.delete_tasks_for_month("") == 0
