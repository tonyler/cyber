from __future__ import annotations

from typing import List

from logger_config import setup_logger

logger = setup_logger(__name__)


class MembersSyncService:
    def __init__(self, sheets_service, parser, members_db, activity_history_sheet_id: str) -> None:
        self.sheets_service = sheets_service
        self.parser = parser
        self.members_db = members_db
        self.activity_history_sheet_id = activity_history_sheet_id

    def run(self) -> None:
        synced_tasks = self._sync_coordinated_tasks()
        x_count = self._sync_x_activity_log()
        reddit_count = self._sync_reddit_activity_log()
        self._update_member_aggregates()
        self._update_task_participation_counts()

        logger.info(
            "Members sync completed: tasks=%s x_activities=%s reddit_activities=%s",
            synced_tasks,
            x_count,
            reddit_count,
        )

    def _sync_coordinated_tasks(self) -> int:
        try:
            range_name = "'Coordinated Tasks'!A:H"
            rows = self._fetch_sheet_data(self.activity_history_sheet_id, range_name)

            tasks = self.parser.parse_coordinated_tasks(rows)

            synced_count = 0
            for task in tasks:
                if self.members_db.upsert_task(task):
                    synced_count += 1

            return synced_count

        except Exception as e:
            logger.error(f"Error syncing coordinated tasks: {str(e)}", exc_info=True)
            return 0

    def _sync_x_activity_log(self) -> int:
        try:
            range_name = "'X Activity Log'!A:K"
            rows = self._fetch_sheet_data(self.activity_history_sheet_id, range_name)

            activities = self.parser.parse_x_activity_log(rows)

            inserted_count = self.members_db.insert_x_activities_batch(activities)

            return inserted_count

        except Exception as e:
            logger.error(f"Error syncing X activity log: {str(e)}", exc_info=True)
            return 0

    def _sync_reddit_activity_log(self) -> int:
        try:
            range_name = "'Reddit Activity Log'!A:K"
            rows = self._fetch_sheet_data(self.activity_history_sheet_id, range_name)

            activities = self.parser.parse_reddit_activity_log(rows)

            inserted_count = self.members_db.insert_reddit_activities_batch(activities)

            return inserted_count

        except Exception as e:
            logger.error(f"Error syncing Reddit activity log: {str(e)}", exc_info=True)
            return 0

    def _update_member_aggregates(self) -> None:
        try:
            members = self.members_db.get_active_members()

            for member in members:
                discord_user = member["discord_user"]

                stats = self.members_db.get_member_stats(discord_user)

                if stats:
                    update_data = {
                        "discord_user": discord_user,
                        "last_active": stats["last_active"],
                        "total_tasks": stats["total_tasks"],
                    }

                    update_data.update(
                        {
                            "x_profile_url": member.get("x_profile_url"),
                            "reddit_profile_url": member.get("reddit_profile_url"),
                            "x_handle": member.get("x_handle"),
                            "reddit_username": member.get("reddit_username"),
                            "status": member.get("status"),
                            "registration_date": member.get("registration_date"),
                        }
                    )

                    self.members_db.upsert_member(update_data)

            logger.info(f"Updated aggregates for {len(members)} members")

        except Exception as e:
            logger.error(f"Error updating member aggregates: {str(e)}", exc_info=True)

    def _update_task_participation_counts(self) -> None:
        try:
            tasks = self.members_db.get_active_tasks()

            for task in tasks:
                task_id = task["task_id"]

                count = self.members_db.get_task_participation_count(task_id)

                update_data = task.copy()
                update_data["participation_count"] = count

                self.members_db.upsert_task(update_data)

            logger.info(f"Updated participation counts for {len(tasks)} tasks")

        except Exception as e:
            logger.error(f"Error updating task participation counts: {str(e)}", exc_info=True)

    def _fetch_sheet_data(self, spreadsheet_id: str, range_name: str) -> List[List[str]]:
        logger.info(f"Fetching data from: {range_name}")

        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()

            rows = result.get("values", [])
            logger.info(f"✅ Fetched {len(rows)} rows")
            return rows

        except Exception as e:
            logger.error(f"❌ Error fetching sheet data: {str(e)}", exc_info=True)
            raise
