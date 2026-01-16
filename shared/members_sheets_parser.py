"""
Parser for Google Sheets data - converts sheet rows to structured dicts.
"""

import hashlib
import re
from typing import List, Dict, Optional


class MembersSheetsParser:
    """Parse Google Sheets data into structured dictionaries."""

    def parse_members_registry(self, rows: List[List[str]]) -> List[Dict]:
        """
        Parse Member Registry sheet.
        Expected columns: discord_user, x_handle, reddit_username, status, joined_date, ...
        """
        if not rows or len(rows) < 2:
            return []

        headers = [h.lower().strip().replace(' ', '_') for h in rows[0]]
        members = []

        for row in rows[1:]:
            if not row or not row[0].strip():
                continue

            member = {}
            for i, header in enumerate(headers):
                value = row[i].strip() if i < len(row) else ''
                member[header] = value

            # Normalize field names
            if 'discord_user' not in member and 'discord' in member:
                member['discord_user'] = member.get('discord', '')
            if 'x_handle' not in member and 'twitter' in member:
                member['x_handle'] = member.get('twitter', '')

            if member.get('discord_user'):
                members.append(member)

        return members

    def parse_monthly_content_tasks(self, rows: List[List[str]], year_month: str) -> List[Dict]:
        """
        Parse monthly content tasks sheet.
        Expected columns: author, url, impressions, likes, comments, content, title, ...
        """
        if not rows or len(rows) < 2:
            return []

        headers = [h.lower().strip().replace(' ', '_') for h in rows[0]]
        tasks = []

        for row in rows[1:]:
            if not row:
                continue

            task = {}
            for i, header in enumerate(headers):
                value = row[i].strip() if i < len(row) else ''
                task[header] = value

            # Get URL - try multiple possible column names
            url = (task.get('url') or task.get('target_url') or
                   task.get('link') or task.get('post_url') or '').strip()

            if not url:
                continue

            # Normalize URL
            url = self._normalize_url(url)

            # Determine platform from URL
            platform = 'x'
            if 'reddit.com' in url:
                platform = 'reddit'

            # Generate task_id from URL
            task_id = hashlib.sha1(url.encode()).hexdigest()

            # Parse numeric fields
            impressions = self._parse_int(task.get('impressions') or task.get('views') or '0')
            likes = self._parse_int(task.get('likes') or task.get('upvotes') or '0')
            comments = self._parse_int(task.get('comments') or task.get('replies') or '0')

            tasks.append({
                'task_id': task_id,
                'platform': platform,
                'task_type': 'content',
                'target_url': url,
                'description': task.get('description', ''),
                'content': task.get('content', ''),
                'title': task.get('title', ''),
                'impressions': impressions,
                'likes': likes,
                'comments': comments,
                'is_active': 1,
                'created_date': task.get('created_date') or task.get('date', ''),
                'created_by': task.get('author') or task.get('created_by', ''),
                'year_month': year_month,
            })

        return tasks

    def parse_x_activity_log(self, rows: List[List[str]]) -> List[Dict]:
        """
        Parse X activity log from sheet.
        Expected columns: date, time, discord_user, x_handle, activity_type, activity_url, target_url, task_id, notes
        """
        if not rows or len(rows) < 2:
            return []

        # Expected column order
        expected = ['date', 'time', 'discord_user', 'x_handle', 'activity_type',
                    'activity_url', 'target_url', 'task_id', 'notes']

        activities = []
        for row in rows[1:]:
            if not row or len(row) < 3:
                continue

            activity = {}
            for i, key in enumerate(expected):
                activity[key] = row[i].strip() if i < len(row) else ''

            # Skip if no user or activity
            if not activity.get('discord_user') and not activity.get('x_handle'):
                continue

            activities.append(activity)

        return activities

    def parse_reddit_activity_log(self, rows: List[List[str]]) -> List[Dict]:
        """
        Parse Reddit activity log from sheet.
        Expected columns: date, time, discord_user, reddit_username, activity_type, activity_url, target_url, task_id, notes
        """
        if not rows or len(rows) < 2:
            return []

        expected = ['date', 'time', 'discord_user', 'reddit_username', 'activity_type',
                    'activity_url', 'target_url', 'task_id', 'notes']

        activities = []
        for row in rows[1:]:
            if not row or len(row) < 3:
                continue

            activity = {}
            for i, key in enumerate(expected):
                activity[key] = row[i].strip() if i < len(row) else ''

            if not activity.get('discord_user') and not activity.get('reddit_username'):
                continue

            activities.append(activity)

        return activities

    def _normalize_url(self, url: str) -> str:
        """Normalize URL format."""
        if not url:
            return url

        # Handle X/Twitter URLs
        match = re.search(r'/status(?:es)?/(\d+)', url)
        if match:
            return f"https://x.com/i/status/{match.group(1)}"

        # Ensure https
        if url and not url.startswith('http'):
            url = f"https://{url.lstrip('/')}"

        return url

    def _parse_int(self, value: str) -> int:
        """Parse integer from string, handling K/M suffixes."""
        if not value:
            return 0

        value = str(value).strip().upper().replace(',', '')

        match = re.match(r'([\d.]+)([KMB])?', value)
        if not match:
            return 0

        number = float(match.group(1))
        suffix = match.group(2)

        if suffix == 'K':
            return int(number * 1000)
        elif suffix == 'M':
            return int(number * 1_000_000)
        elif suffix == 'B':
            return int(number * 1_000_000_000)

        return int(number)
