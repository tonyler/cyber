"""
Shared service for Google Sheets member operations.
Used by bot for direct writes, ensures Google Sheets is source of truth for members.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SheetsMemberService:
    """Service for member CRUD operations on Google Sheets."""

    def __init__(self, credentials_file: Path, sheet_id: str):
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self._client = None
        self._worksheet = None

    def _get_client(self):
        """Lazy-load gspread client."""
        if self._client is None:
            import gspread
            self._client = gspread.service_account(filename=str(self.credentials_file))
        return self._client

    def _get_worksheet(self):
        """Get the Member Registry worksheet, creating if needed."""
        if self._worksheet is None:
            gc = self._get_client()
            spreadsheet = gc.open_by_key(self.sheet_id)
            try:
                self._worksheet = spreadsheet.worksheet("Member Registry")
            except Exception:
                headers = [
                    'discord_user', 'x_handle', 'reddit_username', 'status',
                    'joined_date', 'last_activity', 'total_points', 'last_active',
                    'total_tasks', 'x_profile_url', 'reddit_profile_url', 'registration_date'
                ]
                self._worksheet = spreadsheet.add_worksheet(
                    title="Member Registry", rows=500, cols=len(headers)
                )
                self._worksheet.update(values=[headers], range_name='A1')
        return self._worksheet

    def find_member_row(self, discord_user: str) -> Optional[int]:
        """Find row index (1-based) for a discord user, or None if not found."""
        try:
            worksheet = self._get_worksheet()
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                return None

            discord_lower = discord_user.lower()
            for row_idx, row in enumerate(all_values[1:], start=2):
                if row and row[0].lower() == discord_lower:
                    return row_idx
            return None
        except Exception as e:
            logger.error(f"Error finding member row: {e}")
            return None

    def upsert_member(self, discord_user: str, x_handle: str, reddit_username: str) -> bool:
        """Insert or update a member in Google Sheets.

        Preserves existing fields (joined_date, total_points, etc.) on updates.
        Returns True on success, False on failure.
        """
        try:
            worksheet = self._get_worksheet()
            row_idx = self.find_member_row(discord_user)
            today = datetime.now().strftime('%Y-%m-%d')

            if row_idx:
                # Update existing - preserve certain fields
                existing_row = worksheet.row_values(row_idx)

                # Pad row to ensure we have all columns
                while len(existing_row) < 12:
                    existing_row.append('')

                # Update only specific fields, preserve others
                updated_row = [
                    discord_user,                    # A: discord_user
                    x_handle,                        # B: x_handle (update)
                    reddit_username,                 # C: reddit_username (update)
                    existing_row[3] or 'active',     # D: status (preserve)
                    existing_row[4] or today,        # E: joined_date (preserve)
                    existing_row[5],                 # F: last_activity (preserve)
                    existing_row[6] or '0',          # G: total_points (preserve)
                    today,                           # H: last_active (update)
                    existing_row[8],                 # I: total_tasks (preserve)
                    f'https://x.com/{x_handle}' if x_handle else '',  # J: x_profile_url
                    f'https://reddit.com/user/{reddit_username}' if reddit_username else '',  # K: reddit_profile_url
                    existing_row[11] or today,       # L: registration_date (preserve)
                ]

                worksheet.update(values=[updated_row], range_name=f'A{row_idx}:L{row_idx}')
                logger.info(f"Updated member in sheets: {discord_user}")
            else:
                # New member - append row
                new_row = [
                    discord_user,                    # A: discord_user
                    x_handle,                        # B: x_handle
                    reddit_username,                 # C: reddit_username
                    'active',                        # D: status
                    today,                           # E: joined_date
                    '',                              # F: last_activity
                    '0',                             # G: total_points
                    today,                           # H: last_active
                    '',                              # I: total_tasks
                    f'https://x.com/{x_handle}' if x_handle else '',  # J: x_profile_url
                    f'https://reddit.com/user/{reddit_username}' if reddit_username else '',  # K: reddit_profile_url
                    today,                           # L: registration_date
                ]

                worksheet.append_row(new_row, value_input_option='RAW')
                logger.info(f"Added new member to sheets: {discord_user}")

            return True

        except Exception as e:
            logger.error(f"Failed to upsert member to sheets: {e}")
            return False
