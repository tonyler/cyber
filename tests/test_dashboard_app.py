"""Tests for dashboard3/app.py helper and route behavior."""

import app as dashboard_app


class FakeMembersService:
    def __init__(self):
        self.tasks_by_month = {
            "2026-01": [
                {
                    "platform": "x",
                    "task_type": "content",
                    "impressions": "100",
                    "title": "Jan X",
                    "target_url": "https://x.com/i/status/1",
                },
                {
                    "platform": "reddit",
                    "task_type": "content",
                    "impressions": "25",
                    "title": "Jan Reddit",
                    "target_url": "https://reddit.com/r/test/comments/1",
                },
            ],
            "2026-02": [
                {
                    "platform": "x",
                    "task_type": "content",
                    "impressions": "300",
                    "title": "Feb X",
                    "target_url": "https://x.com/i/status/2",
                },
            ],
        }

    def get_tasks_for_month(self, month):
        if not month:
            return self.tasks_by_month["2026-01"] + self.tasks_by_month["2026-02"]
        return list(self.tasks_by_month.get(month, []))

    def get_available_task_months(self):
        return ["2026-02", "2026-01"]

    def get_all_members(self):
        return [{"discord_user": "alice", "x_handle": "alice_x", "status": "active"}]

    def get_available_activity_months(self):
        return ["2026-02", "2026-01"]

    def get_member_contribution_stats(self, discord_user, month=""):
        if month == "2026-01":
            return {
                "x_comments": 1,
                "x_quotes": 0,
                "x_retweets": 0,
                "reddit_comments": 2,
                "total_contributions": 3,
            }
        return {
            "x_comments": 5,
            "x_quotes": 1,
            "x_retweets": 1,
            "reddit_comments": 4,
            "total_contributions": 11,
        }

    def get_combined_activity_history(self, month=""):
        return [
            {
                "platform": "x",
                "discord_user": "alice",
                "username_label": "@alice_x",
                "date": "2026-01-10",
                "time": "10:00:00",
                "activity_type": "comment",
            }
        ]


class TestApiStats:
    def test_uses_selected_month_instead_of_current_month(self, monkeypatch):
        monkeypatch.setattr(dashboard_app, "members_service", FakeMembersService())

        with dashboard_app.app.test_request_context("/api/stats?month=2026-01"):
            response = dashboard_app.api_stats.__wrapped__()

        assert response.get_json() == {
            "impressions_total": 125,
            "x_posts": 1,
            "reddit_posts": 1,
            "month": "2026-01",
        }


class TestIndexRoute:
    def test_all_time_scope_uses_all_tasks_and_disables_monthly_charts(self, monkeypatch):
        monkeypatch.setattr(dashboard_app, "members_service", FakeMembersService())
        monkeypatch.setattr(dashboard_app, "render_template", lambda template, **context: context)

        with dashboard_app.app.test_request_context("/?month="):
            context = dashboard_app.index.__wrapped__()

        assert context["selected_month"] == ""
        assert context["stats"] == {
            "impressions_total": 425,
            "x_posts": 2,
            "reddit_posts": 1,
        }
        assert context["show_performance_charts"] is False
        assert context["performance_scope_label"] == "All Time"


class TestMembersRoute:
    def test_members_page_uses_month_scoped_contribution_stats(self, monkeypatch):
        monkeypatch.setattr(dashboard_app, "members_service", FakeMembersService())
        monkeypatch.setattr(dashboard_app, "render_template", lambda template, **context: context)

        with dashboard_app.app.test_request_context("/members?month=2026-01"):
            context = dashboard_app.members.__wrapped__()

        assert context["selected_month"] == "2026-01"
        assert context["selected_scope_label"] == "2026-01"
        assert context["members"][0]["total_contributions"] == 3
        assert context["members"][0]["reddit_comments"] == 2
