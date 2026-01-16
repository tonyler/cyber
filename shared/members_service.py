"""
Members database service for reading members, tasks, and activity data from CSVs.
"""

import csv
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class MembersDBService:
    """Service for accessing member data and activities from CSV files."""

    def __init__(self, members_db_path: str):
        self.members_db_path = Path(members_db_path)
        self.db_dir = self.members_db_path.parent
        self.tasks_path = self.db_dir / "links.csv"
        self.x_activity_path = self.db_dir / "x_activity_log.csv"
        self.reddit_activity_path = self.db_dir / "reddit_activity_log.csv"

    def _read_csv(self, path: Path) -> List[Dict]:
        """Read a CSV file and return list of dicts."""
        if not path.exists():
            return []
        try:
            with path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            return []

    def get_all_members(self) -> List[Dict]:
        """Get all members from the database."""
        return self._read_csv(self.members_db_path)

    def get_active_members(self) -> List[Dict]:
        """Get all active members."""
        members = self.get_all_members()
        return [m for m in members if m.get('status', '').lower() == 'active']

    def get_member_by_x_handle(self, x_handle: str) -> Optional[Dict]:
        """Find a member by their X handle."""
        if not x_handle:
            return None
        x_handle_lower = x_handle.lower().lstrip('@')
        for member in self.get_all_members():
            member_handle = (member.get('x_handle') or '').lower().lstrip('@')
            if member_handle == x_handle_lower:
                return member
        return None

    def get_member_by_reddit_username(self, reddit_username: str) -> Optional[Dict]:
        """Find a member by their Reddit username."""
        if not reddit_username:
            return None
        reddit_lower = reddit_username.lower().lstrip('u/')
        for member in self.get_all_members():
            member_reddit = (member.get('reddit_username') or '').lower().lstrip('u/')
            if member_reddit == reddit_lower:
                return member
        return None

    def get_tasks_for_month(self, year_month: str = '') -> List[Dict]:
        """Get tasks/links for a specific month (format: YYYY-MM) or all if empty."""
        tasks = self._read_csv(self.tasks_path)
        # Normalize field names for backward compatibility
        for t in tasks:
            if 'url' in t and 'target_url' not in t:
                t['target_url'] = t['url']
            if 'author' in t and 'created_by' not in t:
                t['created_by'] = t['author']
            # Default task_type to 'content' for dashboard display
            if 'task_type' not in t:
                t['task_type'] = 'content'
        if not year_month:
            return tasks
        return [t for t in tasks if t.get('year_month', '') == year_month]

    def get_x_activities_by_member(self, discord_user: str) -> List[Dict]:
        """Get X activities for a specific member."""
        if not discord_user:
            return []
        activities = self._read_csv(self.x_activity_path)
        discord_lower = discord_user.lower()
        return [a for a in activities if (a.get('discord_user') or '').lower() == discord_lower]

    def get_reddit_activities_by_member(self, discord_user: str) -> List[Dict]:
        """Get Reddit activities for a specific member."""
        if not discord_user:
            return []
        activities = self._read_csv(self.reddit_activity_path)
        discord_lower = discord_user.lower()
        return [a for a in activities if (a.get('discord_user') or '').lower() == discord_lower]

    def get_x_activity_urls_for_target(self, target_url: str) -> set:
        """Get set of activity URLs already recorded for a target URL."""
        activities = self._read_csv(self.x_activity_path)
        urls = set()
        for a in activities:
            if a.get('target_url', '') == target_url:
                activity_url = a.get('activity_url', '')
                if activity_url:
                    urls.add(activity_url)
        return urls

    def get_combined_activity_history(self, month: str = '') -> List[Dict]:
        """Get combined X and Reddit activity history for a month."""
        x_activities = self._read_csv(self.x_activity_path)
        reddit_activities = self._read_csv(self.reddit_activity_path)

        # Add platform tag
        for a in x_activities:
            a['platform'] = 'x'
        for a in reddit_activities:
            a['platform'] = 'reddit'

        all_activities = x_activities + reddit_activities

        # Filter by month if specified
        if month:
            filtered = []
            for a in all_activities:
                activity_date = a.get('date', '')
                if activity_date and activity_date.startswith(month):
                    filtered.append(a)
            all_activities = filtered

        # Sort by date and time descending
        def sort_key(a):
            date = a.get('date', '')
            time = a.get('time', '')
            return f"{date} {time}"

        all_activities.sort(key=sort_key, reverse=True)
        return all_activities

    # ========== Write Methods ==========

    def _write_csv(self, path: Path, rows: List[Dict], fieldnames: List[str]) -> bool:
        """Write rows to a CSV file."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + '.tmp')
            with tmp_path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            tmp_path.replace(path)
            return True
        except Exception:
            return False

    def upsert_member(self, member: Dict) -> bool:
        """Insert or update a member."""
        if not member.get('discord_user'):
            return False

        members = self.get_all_members()
        fieldnames = ['discord_user', 'x_handle', 'reddit_username', 'status',
                      'joined_date', 'last_activity', 'total_points', 'last_active',
                      'total_tasks', 'x_profile_url', 'reddit_profile_url', 'registration_date']

        # Find existing member
        discord_lower = member['discord_user'].lower()
        found = False
        for i, m in enumerate(members):
            if (m.get('discord_user') or '').lower() == discord_lower:
                # Update existing
                members[i] = {**m, **member}
                found = True
                break

        if not found:
            members.append(member)

        return self._write_csv(self.members_db_path, members, fieldnames)

    def upsert_task(self, task: Dict) -> bool:
        """Insert or update a task/link."""
        # Use url or target_url as identifier
        task_url = task.get('url') or task.get('target_url')
        if not task_url:
            return False

        tasks = self._read_csv(self.tasks_path)
        fieldnames = ['id', 'platform', 'url', 'author', 'year_month', 'date',
                      'impressions', 'likes', 'comments', 'retweets',
                      'content', 'title', 'synced_at']

        # Normalize task data to new schema
        normalized = {
            'id': task.get('id') or task.get('task_id', ''),
            'platform': task.get('platform', 'x'),
            'url': task_url,
            'author': task.get('author') or task.get('created_by', ''),
            'year_month': task.get('year_month', ''),
            'date': task.get('date') or task.get('created_date', ''),
            'impressions': task.get('impressions', ''),
            'likes': task.get('likes', ''),
            'comments': task.get('comments', ''),
            'retweets': task.get('retweets', ''),
            'content': task.get('content', ''),
            'title': task.get('title', ''),
            'synced_at': task.get('synced_at', ''),
        }

        # Find existing by URL
        found = False
        for i, t in enumerate(tasks):
            existing_url = t.get('url') or t.get('target_url', '')
            if existing_url == task_url:
                tasks[i] = {**t, **normalized}
                found = True
                break

        if not found:
            tasks.append(normalized)

        return self._write_csv(self.tasks_path, tasks, fieldnames)

    def delete_tasks_for_month(self, year_month: str) -> int:
        """Delete all tasks/links for a specific month. Returns count of deleted."""
        if not year_month:
            return 0

        tasks = self._read_csv(self.tasks_path)
        original_count = len(tasks)
        tasks = [t for t in tasks if t.get('year_month') != year_month]
        deleted = original_count - len(tasks)

        if deleted > 0:
            fieldnames = ['id', 'platform', 'url', 'author', 'year_month', 'date',
                          'impressions', 'likes', 'comments', 'retweets',
                          'content', 'title', 'synced_at']
            self._write_csv(self.tasks_path, tasks, fieldnames)

        return deleted

    def insert_x_activities_batch(self, activities: List[Dict]) -> int:
        """Insert X activities, skipping duplicates. Returns count inserted."""
        if not activities:
            return 0

        existing = self._read_csv(self.x_activity_path)
        existing_urls = {a.get('activity_url', '') for a in existing if a.get('activity_url')}

        fieldnames = ['date', 'time', 'discord_user', 'x_handle', 'activity_type',
                      'activity_url', 'target_url', 'task_id', 'notes']

        inserted = 0
        for activity in activities:
            activity_url = activity.get('activity_url', '')
            if activity_url and activity_url not in existing_urls:
                existing.append(activity)
                existing_urls.add(activity_url)
                inserted += 1

        if inserted > 0:
            self._write_csv(self.x_activity_path, existing, fieldnames)

        return inserted

    def insert_reddit_activities_batch(self, activities: List[Dict]) -> int:
        """Insert Reddit activities, skipping duplicates. Returns count inserted."""
        if not activities:
            return 0

        existing = self._read_csv(self.reddit_activity_path)
        existing_urls = {a.get('activity_url', '') for a in existing if a.get('activity_url')}

        fieldnames = ['date', 'time', 'discord_user', 'reddit_username', 'activity_type',
                      'activity_url', 'target_url', 'task_id', 'notes']

        inserted = 0
        for activity in activities:
            activity_url = activity.get('activity_url', '')
            if activity_url and activity_url not in existing_urls:
                existing.append(activity)
                existing_urls.add(activity_url)
                inserted += 1

        if inserted > 0:
            self._write_csv(self.reddit_activity_path, existing, fieldnames)

        return inserted
