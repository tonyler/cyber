from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from logger_config import setup_logger
from csv_store import load_csv, merge_fieldnames, write_csv, locked_csv

logger = setup_logger(__name__)

DEFAULT_MEMBER_FIELDS = [
    "discord_user",
    "x_handle",
    "reddit_username",
    "status",
    "joined_date",
    "last_activity",
    "total_points",
    "last_active",
    "total_tasks",
    "x_profile_url",
    "reddit_profile_url",
    "registration_date",
]

DEFAULT_TASK_FIELDS = [
    "task_id",
    "platform",
    "task_type",
    "action_type",
    "target_url",
    "description",
    "is_active",
    "created_date",
    "created_by",
    "deadline",
    "participation_count",
    "year_month",
    "impressions",
    "likes",
    "comments",
]

DEFAULT_X_ACTIVITY_FIELDS = [
    "date",
    "time",
    "discord_user",
    "x_handle",
    "activity_type",
    "activity_url",
    "target_url",
    "task_id",
    "notes",
]

DEFAULT_REDDIT_ACTIVITY_FIELDS = [
    "date",
    "time",
    "discord_user",
    "reddit_username",
    "activity_type",
    "activity_url",
    "target_url",
    "task_id",
    "upvotes",
    "comments",
    "notes",
]


class MembersDBService:
    def __init__(self, db_path: str):
        base_dir = Path(db_path).parent
        self.members_path = str(Path(db_path))
        self.tasks_path = str(base_dir / "coordinated_tasks.csv")
        self.x_activity_path = str(base_dir / "x_activity_log.csv")
        self.reddit_activity_path = str(base_dir / "reddit_activity_log.csv")

        if not Path(self.members_path).exists():
            logger.warning(f"Members CSV not found at {self.members_path}, it will be created on write")

    def _read_table(self, path: str, default_fields: List[str]) -> tuple[List[str], List[Dict[str, str]]]:
        fields, rows = load_csv(path)
        if not fields:
            fields = list(default_fields)
        return fields, rows

    def _write_table(self, path: str, fields: List[str], rows: List[Dict[str, str]]) -> None:
        write_csv(path, fields, rows)

    def _parse_int(self, value: Optional[str]) -> int:
        if value is None:
            return 0
        try:
            return int(str(value).replace(",", "").strip())
        except ValueError:
            return 0

    def _parse_date(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    def _parse_datetime(self, date_value: Optional[str], time_value: Optional[str]) -> Optional[datetime]:
        if not date_value:
            return None
        time_value = time_value or "00:00:00"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(f"{date_value} {time_value}", fmt)
            except ValueError:
                continue
        try:
            return datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            return None

    def _is_active(self, value: Optional[str]) -> bool:
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes"}

    def _upsert_by_key(self, rows: List[Dict[str, str]], key_field: str, data: Dict) -> bool:
        key = data.get(key_field)
        if not key:
            return False
        for row in rows:
            if row.get(key_field) == key:
                for field, value in data.items():
                    row[field] = "" if value is None else value
                return True
        rows.append({field: "" if value is None else value for field, value in data.items()})
        return True

    def get_all_members(self) -> List[Dict]:
        try:
            _, rows = self._read_table(self.members_path, DEFAULT_MEMBER_FIELDS)
            rows.sort(key=lambda r: r.get("discord_user", ""))
            return rows
        except Exception as e:
            logger.error(f"Error getting all members: {str(e)}", exc_info=True)
            return []

    def get_active_members(self) -> List[Dict]:
        try:
            _, rows = self._read_table(self.members_path, DEFAULT_MEMBER_FIELDS)
            active = [row for row in rows if row.get("status", "").lower() == "active"]
            active.sort(key=lambda r: r.get("discord_user", ""))
            return active
        except Exception as e:
            logger.error(f"Error getting active members: {str(e)}", exc_info=True)
            return []

    def get_member(self, discord_user: str) -> Optional[Dict]:
        try:
            _, rows = self._read_table(self.members_path, DEFAULT_MEMBER_FIELDS)
            for row in rows:
                if row.get("discord_user") == discord_user:
                    return row
            return None
        except Exception as e:
            logger.error(f"Error getting member {discord_user}: {str(e)}", exc_info=True)
            return None

    def upsert_member(self, member_data: Dict) -> bool:
        try:
            with locked_csv(self.members_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_MEMBER_FIELDS)
                normalized = dict(member_data)
                normalized.setdefault("status", "active")
                normalized.setdefault("total_points", 0)
                fields = merge_fieldnames(fields, normalized.keys())
                updated = self._upsert_by_key(rows, "discord_user", normalized)
                if updated:
                    write(fields, rows)
                return updated
        except Exception as e:
            logger.error(f"Error upserting member: {str(e)}", exc_info=True)
            return False

    def upsert_task(self, task_data: Dict) -> bool:
        try:
            with locked_csv(self.tasks_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_TASK_FIELDS)
                normalized = dict(task_data)
                normalized.setdefault("is_active", 1)
                normalized.setdefault("impressions", 0)
                normalized.setdefault("likes", 0)
                normalized.setdefault("comments", 0)
                fields = merge_fieldnames(fields, normalized.keys())
                updated = self._upsert_by_key(rows, "task_id", normalized)
                if updated:
                    write(fields, rows)
                return updated
        except Exception as e:
            logger.error(f"Error upserting task: {str(e)}", exc_info=True)
            return False

    def delete_tasks_for_month(self, year_month: str) -> int:
        try:
            with locked_csv(self.tasks_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_TASK_FIELDS)
                kept = [row for row in rows if row.get("year_month") != year_month]
                removed = len(rows) - len(kept)
                if removed:
                    write(fields, kept)
                return removed
        except Exception as e:
            logger.error(f"Error deleting tasks for month {year_month}: {str(e)}", exc_info=True)
            return 0

    def get_tasks_for_month(self, year_month: str) -> List[Dict]:
        try:
            _, rows = self._read_table(self.tasks_path, DEFAULT_TASK_FIELDS)
            filtered = [row for row in rows if row.get("year_month") == year_month] if year_month else rows

            def sort_key(row: Dict[str, str]):
                date_value = self._parse_date(row.get("created_date"))
                impressions = self._parse_int(row.get("impressions"))
                task_id = row.get("task_id", "")
                return (date_value or datetime.min, impressions, task_id)

            filtered.sort(key=sort_key, reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error getting tasks for month {year_month}: {str(e)}", exc_info=True)
            return []

    def get_active_tasks(self, platform: str = None) -> List[Dict]:
        try:
            _, rows = self._read_table(self.tasks_path, DEFAULT_TASK_FIELDS)
            active = [row for row in rows if self._is_active(row.get("is_active"))]
            if platform:
                active = [row for row in active if row.get("platform") == platform]

            active.sort(key=lambda r: self._parse_date(r.get("created_date")) or datetime.min, reverse=True)
            return active
        except Exception as e:
            logger.error(f"Error getting active tasks: {str(e)}", exc_info=True)
            return []

    def get_task_by_id(self, task_id: str) -> Optional[Dict]:
        try:
            _, rows = self._read_table(self.tasks_path, DEFAULT_TASK_FIELDS)
            for row in rows:
                if row.get("task_id") == task_id:
                    return row
            return None
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {str(e)}", exc_info=True)
            return None

    def insert_x_activity(self, activity_data: Dict) -> bool:
        inserted = self.insert_x_activities_batch([activity_data])
        return inserted > 0

    def insert_x_activities_batch(self, activities: List[Dict]) -> int:
        if not activities:
            logger.info("Inserted 0/0 X activities")
            return 0

        try:
            with locked_csv(self.x_activity_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_X_ACTIVITY_FIELDS)
                fields = merge_fieldnames(fields, activities[0].keys())
                existing = {
                    (row.get("discord_user"), row.get("activity_url"))
                    for row in rows
                    if row.get("discord_user") and row.get("activity_url")
                }

                inserted_rows = 0
                for activity in activities:
                    key = (activity.get("discord_user"), activity.get("activity_url"))
                    if not key[0] or not key[1] or key in existing:
                        continue
                    existing.add(key)
                    rows.append({field: "" if value is None else value for field, value in activity.items()})
                    inserted_rows += 1

                if inserted_rows:
                    write(fields, rows)

                logger.info(f"Inserted {inserted_rows}/{len(activities)} X activities")
                return inserted_rows
        except Exception as e:
            logger.error(f"Error inserting X activities batch: {str(e)}", exc_info=True)
            return 0

    def insert_reddit_activity(self, activity_data: Dict) -> bool:
        inserted = self.insert_reddit_activities_batch([activity_data])
        return inserted > 0

    def insert_reddit_activities_batch(self, activities: List[Dict]) -> int:
        if not activities:
            logger.info("Inserted 0/0 Reddit activities")
            return 0

        try:
            with locked_csv(self.reddit_activity_path) as (fields, rows, write):
                if not fields:
                    fields = list(DEFAULT_REDDIT_ACTIVITY_FIELDS)
                fields = merge_fieldnames(fields, activities[0].keys())
                existing = {
                    (row.get("discord_user"), row.get("activity_url"))
                    for row in rows
                    if row.get("discord_user") and row.get("activity_url")
                }

                inserted_rows = 0
                for activity in activities:
                    key = (activity.get("discord_user"), activity.get("activity_url"))
                    if not key[0] or not key[1] or key in existing:
                        continue
                    existing.add(key)
                    rows.append({field: "" if value is None else value for field, value in activity.items()})
                    inserted_rows += 1

                if inserted_rows:
                    write(fields, rows)

                logger.info(f"Inserted {inserted_rows}/{len(activities)} Reddit activities")
                return inserted_rows
        except Exception as e:
            logger.error(f"Error inserting Reddit activities batch: {str(e)}", exc_info=True)
            return 0

    def get_x_activities_by_member(self, discord_user: str) -> List[Dict]:
        try:
            _, rows = self._read_table(self.x_activity_path, DEFAULT_X_ACTIVITY_FIELDS)
            filtered = [row for row in rows if row.get("discord_user") == discord_user]
            filtered.sort(key=lambda r: self._parse_datetime(r.get("date"), r.get("time")) or datetime.min, reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error getting X activities for {discord_user}: {str(e)}", exc_info=True)
            return []

    def get_reddit_activities_by_member(self, discord_user: str) -> List[Dict]:
        try:
            _, rows = self._read_table(self.reddit_activity_path, DEFAULT_REDDIT_ACTIVITY_FIELDS)
            filtered = [row for row in rows if row.get("discord_user") == discord_user]
            filtered.sort(key=lambda r: self._parse_datetime(r.get("date"), r.get("time")) or datetime.min, reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error getting Reddit activities for {discord_user}: {str(e)}", exc_info=True)
            return []

    def get_x_activities_by_task(self, task_id: str) -> List[Dict]:
        try:
            _, rows = self._read_table(self.x_activity_path, DEFAULT_X_ACTIVITY_FIELDS)
            filtered = [row for row in rows if row.get("task_id") == task_id]
            filtered.sort(key=lambda r: self._parse_datetime(r.get("date"), r.get("time")) or datetime.min, reverse=True)
            return filtered
        except Exception as e:
            logger.error(f"Error getting X activities for task {task_id}: {str(e)}", exc_info=True)
            return []

    def get_x_activity_urls_for_target(self, target_url: str) -> List[str]:
        try:
            _, rows = self._read_table(self.x_activity_path, DEFAULT_X_ACTIVITY_FIELDS)
            return [
                row.get("activity_url")
                for row in rows
                if row.get("target_url") == target_url and row.get("activity_url")
            ]
        except Exception as e:
            logger.error(f"Error getting X activity URLs for target {target_url}: {str(e)}", exc_info=True)
            return []

    def get_member_stats(self, discord_user: str) -> Optional[Dict]:
        try:
            x_rows = self.get_x_activities_by_member(discord_user)
            reddit_rows = self.get_reddit_activities_by_member(discord_user)
            all_rows = x_rows + reddit_rows
            if not all_rows:
                return None

            latest = None
            for row in all_rows:
                dt = self._parse_datetime(row.get("date"), row.get("time"))
                if dt and (latest is None or dt > latest):
                    latest = dt

            return {
                "last_active": latest.strftime("%Y-%m-%d") if latest else None,
                "total_tasks": len(all_rows),
            }
        except Exception as e:
            logger.error(f"Error getting member stats for {discord_user}: {str(e)}", exc_info=True)
            return None

    def get_task_participation_count(self, task_id: str) -> int:
        try:
            x_rows = self.get_x_activities_by_task(task_id)
            _, reddit_rows = self._read_table(self.reddit_activity_path, DEFAULT_REDDIT_ACTIVITY_FIELDS)
            reddit_rows = [row for row in reddit_rows if row.get("task_id") == task_id]
            return len(x_rows) + len(reddit_rows)
        except Exception as e:
            logger.error(f"Error getting participation count for {task_id}: {str(e)}", exc_info=True)
            return 0

    def get_combined_activity_history(self, year_month: str = None) -> List[Dict]:
        """Get all contributions from both X and Reddit within the selected month."""
        try:
            _, x_rows = self._read_table(self.x_activity_path, DEFAULT_X_ACTIVITY_FIELDS)
            _, reddit_rows = self._read_table(self.reddit_activity_path, DEFAULT_REDDIT_ACTIVITY_FIELDS)

            combined = []
            for row in x_rows:
                if year_month and not str(row.get("date", "")).startswith(year_month):
                    continue
                combined.append({
                    "platform": "x",
                    "date": row.get("date"),
                    "time": row.get("time"),
                    "discord_user": row.get("discord_user"),
                    "username": row.get("x_handle"),
                    "activity_type": row.get("activity_type"),
                    "activity_url": row.get("activity_url"),
                    "target_url": row.get("target_url"),
                    "task_id": row.get("task_id"),
                    "notes": row.get("notes"),
                })

            for row in reddit_rows:
                if year_month and not str(row.get("date", "")).startswith(year_month):
                    continue
                combined.append({
                    "platform": "reddit",
                    "date": row.get("date"),
                    "time": row.get("time"),
                    "discord_user": row.get("discord_user"),
                    "username": row.get("reddit_username"),
                    "activity_type": row.get("activity_type"),
                    "activity_url": row.get("activity_url"),
                    "target_url": row.get("target_url"),
                    "task_id": row.get("task_id"),
                    "notes": row.get("notes"),
                })

            combined.sort(
                key=lambda r: self._parse_datetime(r.get("date"), r.get("time")) or datetime.min,
                reverse=True
            )
            return combined
        except Exception as e:
            logger.error(f"Error getting combined activity history: {str(e)}", exc_info=True)
            return []
